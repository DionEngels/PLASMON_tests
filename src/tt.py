# -*- coding: utf-8 -*-
"""
Created on Sun May 31 22:58:08 2020

@author: Dion Engels
PLASMON Data Analysis

Fitters

This package holds all the fitting algorithms of PLASMON.
This includes 2 Gaussian fitters and 3 Phasor fitters.

----------------------------

v0.0.1: Setup: 31/05/2020
v0.1: rainSTORM slow, but working: 04/06/2020
v0.2: optimizations after initial speed check: 17/06/2020
v0.3: optimization after second speed check: 27/06/2020
v0.4: removed all unneeded fitters
v0.5: Three versions of cached fitter
v0.6: FORTRAN enabled without cache, ST
v0.7: cleanup and declare_functions function: 14/07/2020
v0.8: PhasorSum, remove LastFit, rename, and clean up
v0.9: Gaussian fitting (with or without background) and three Phasor fitters: 24/07/2020
v0.9.1: NaN output instead of leaving out, MATLAB ready output
v0.9.2: removed minimum pixel requirement
v1.0: Integrated intensity output for Gaussians: 27/08/2020
v2.0 pre-1: part of v2.0 pre-1: 03/10/2020
v2.0: with TTParts: 30/10/2020
"""
# %% Imports
from __future__ import division, print_function, absolute_import

import numpy as np  # general mathematics + arrays

from scipy.optimize import _minpack, OptimizeResult  # for Gaussian fitter
from scipy.ndimage import median_filter  # for correlation with experiment
from scipy.stats import norm

import src.mbx_fortran as fortran_linalg  # for fast self-made operations for Gaussian fitter
import src.mbx_fortran_tools as fortran_tools  # for fast self-made general operations
from src.class_dataset_and_class_roi import Dataset  # base dataset
from src.tools import change_to_nm
from src.drift_correction import DriftCorrector
from src.nd2_reading import ND2ReaderSelf

from pyfftw import empty_aligned, FFTW    # for FFT for Phasor
from math import pi, atan2  # general mathematics
from cmath import phase  # general mathematics
import multiprocessing as mp
import _thread

__self_made__ = True

MAX_BYTES = 4294967296 // 1  # 4 GB, // 1 for easy tuning

# %% Time trace class


class TimeTrace(Dataset):
    """
    TT Class for every time trace. Inherits from Dataset
    """
    def __init__(self, experiment, nd2, name):
        """
        Initializer of TT. Sets frames, frame_for_roi and metadata
        ------------------------
        :param experiment: parent experiment
        :param nd2: nd2 of TT
        :param name: name of TT
        """
        super().__init__(experiment, nd2, name)
        self.type = "TT"
        self.frames = nd2
        background = median_filter(np.asarray(nd2[0]), size=9)
        self.frame_for_rois = np.asarray(nd2[0]).astype(self.data_type_signed) - background
        self.metadata = nd2.get_metadata()
        try:
            self.time_axis = self.metadata['timesteps']
            self.time_axis_dim = 't'
        except:
            self.time_axis = range(0, len(self.frames))
            self.time_axis_dim = 'frames'
        self.drift_corrector = None
        # parts that the TT dataset is split into
        self.tt_parts = None
        self.tt_parts_done = 0
        # cores used for fitting
        self.n_cores = 1
        # correlation used for long measurement drift
        self.correlation_interval = None

    def prepare_run(self, settings):
        """
        Prepare run of TT. Takes users settings, asks some questions, and sets settings
        :param settings: settings to put in
        :return: None. Edits class
        """
        # check
        if self.experiment.proceed_question("Are you sure?", "You cannot change settings later. "
                                                             "Are you sure everything is set up correctly?") is False:
            return False

        # check cores for Phasor
        if settings['#cores'] > 1 and "Phasor" in settings['method']:
            if self.experiment.proceed_question("Just a heads up", """Phasor will be used with one core since the
            overhead only slows it down""") is False:
                return False
            settings['#cores'] = 1

        # set name and settings
        new_name = settings.pop('name', self.name)
        if self.check_name_validity(new_name) is False:
            self.experiment.error_func("Invalid name", "MATLAB only accepts letters, numbers, and underscores. "
                                                       "I also accept - and spaces (these will become underscores in "
                                                       "MATLAB). Please only use these.")
            return False
        self.set_name(new_name)
        self.settings = settings

        # set cores
        self.n_cores = settings['#cores']
        # take slices and create TTParts
        slices_user, _ = self.parse_start_end(settings['frame_begin'], settings['frame_end'])
        if slices_user.stop is None:
            slices_user = slice(slices_user.start, len(self.frames))
        # set correlation interval
        if self.check_correlation_interval_validity(settings['correlation_interval'], slices_user.stop) is False:
            self.experiment.error_func("Invalid correlation interval",
                                       "This can only be 'Never' or an integer smaller than the last frame set."
                                       " Non-integer number will be rounded.")
            return False
        # create TTParts
        self.tt_parts = self.slices_create_setup(slices_user)

        # set max its
        max_its = self.find_max_its()

        # initializer fitter
        if settings['method'] == "Phasor + Intensity":
            self.fitter = Phasor(settings, self.roi_offset)
        elif settings['method'] == "Phasor":
            self.fitter = PhasorDumb(settings, self.roi_offset)
        elif settings['method'] == "Gaussian - Fit bg":
            self.fitter = GaussianBackground(settings, max_its, 6, self.roi_offset)
            self.settings['max_its'] = max_its
        elif settings['method'] == "Gaussian - Estimate bg":
            self.fitter = Gaussian(settings, max_its, 5, self.roi_offset)
            self.settings['max_its'] = max_its
        else:
            self.fitter = PhasorSum(settings, self.roi_offset)

    def check_correlation_interval_validity(self, correlation_interval, end_frame):
        if correlation_interval == "Never":
            # if never, keep it at none
            return True
        else:
            try:
                # try to convert to int
                correlation_interval = int(correlation_interval)
                if correlation_interval > end_frame:
                    return False
                else:
                    self.correlation_interval = correlation_interval
                    return True
            except:
                # if fails, return false
                return False

    def slices_create_setup(self, slices_user):
        """
        Takes the user input for what part he/she wants fitted of the TT, #cores, max RAM usage, and correlation
        interval, and uses that to create TTParts, parts of the TT dataset to be fitted by a single process
        -----------------------
        :param slices_user: user input for which part of the TT to be fitted
        :return: a list of tt_parts, classes which hold a part of the TT Dataset
        """
        # max frame length to fit in memory
        max_length_memory = MAX_BYTES // self.frame_for_rois.astype(self.data_type).nbytes
        # n_parts to split in to remain in memory
        n_parts = int((slices_user.stop - slices_user.start) // max_length_memory + 1)
        if n_parts > 1:
            # if more than one part needed to remain in memory
            if self.correlation_interval is not None:  # if correlation interval
                split_length = self.correlation_interval
                slices = self.slices_create_fixed_length(slices_user, split_length)
                tt_parts = [TTPart(self.filename, self.frames, part_slice) for part_slice in slices]
                while max_length_memory < split_length * self.n_cores:  # if it still doesn't fit in memory, split again
                    slices, tt_parts = self.slices_split_in_two(slices)
                    split_length /= 2
            else:
                # split in even parts for memory
                slices = self.slices_create(slices_user, n_parts)
                tt_parts = [TTPart(self.filename, self.frames, part_slice) for part_slice in slices]
                if self.n_cores > 1:  # split for cores if needed
                    slices, tt_parts = self.slices_split_for_cores(slices)
        else:  # if fits in memory in one go
            if self.correlation_interval is not None:  # if correlation interval
                slices = self.slices_create_fixed_length(slices_user, self.correlation_interval)
                tt_parts = [TTPart(self.filename, self.frames, part_slice) for part_slice in slices]
                while len(slices) < self.n_cores:  # if fewer slices than cores, split slices
                    slices, tt_parts = self.slices_split_in_two(slices)
            elif self.n_cores > 1:  # if MP
                slices = self.slices_create(slices_user, self.n_cores)
                tt_parts = [TTPart(self.filename, self.frames, part_slice) for part_slice in slices]
            else:  # if single process
                slices = [slices_user]
                tt_parts = [TTPart(self.filename, self.frames, part_slice) for part_slice in slices]

        return tt_parts

    def slices_split_in_two(self, slices):
        """
        Takes a slice and splits it in two. Also creates tt_parts
        --------------------
        :param slices: slices to split in two
        :return: new_slices: new slices
        :return: new_tt_parts: new_tt_parts build with the new slices
        """
        new_slices = []
        new_tt_parts = []
        for one_slice in slices:
            new_slices_part = self.slices_create(one_slice, 2)
            new_slices.extend(new_slices_part)
            new_tt_parts.append(TTPart(self.filename, self.frames, new_slices_part[0]))
            new_tt_parts.append(TTPart(self.filename, self.frames, new_slices_part[1], corr=False))
        return new_slices, new_tt_parts

    def slices_split_for_cores(self, slices):
        """
        Takes a slice and splits it in n parts (the number of cores). Also creates tt_parts
        --------------------
        :param slices: slices to split in two
        :return: new_slices: new slices
        :return: new_tt_parts: new_tt_parts build with the new slices
        """
        new_slices = []
        new_tt_parts = []
        for one_slice in slices:
            new_slices_part = self.slices_create(one_slice, self.n_cores)
            for index, new_slice_ind in enumerate(new_slices_part):
                if index == 0:
                    new_tt_parts.append(TTPart(self.filename, self.frames, new_slice_ind))
                else:
                    new_tt_parts.append(TTPart(self.filename, self.frames, new_slice_ind, corr=False))

        return new_slices, new_tt_parts

    @staticmethod
    def slices_create(main_slice, n_parts):
        """
        The actual workhorse that splits a slice in n_parts
        --------------------------
        :param main_slice: the slice to be split
        :param n_parts: the number of parts to split in
        :return: slices: the new slices created from main_slice in n_parts
        """
        length = (main_slice.stop - main_slice.start) // n_parts
        remainder = (main_slice.stop - main_slice.start) - length * n_parts
        lengths = [length] * n_parts
        for i in range(remainder):
            lengths[i] += 1

        slices = []
        counter = 0
        for length in lengths:
            slices.append(slice(main_slice.start + counter, main_slice.start + counter + length))
            counter += length

        return slices

    @staticmethod
    def slices_create_fixed_length(main_slice, length):
        """
        The actual workhorse that splits a slice in a fixed length
        -------------------------
        :param main_slice: the slice to be split
        :param length: the length of the parts to split in
        :return: slices: the new slices created from main_slice with length
        """
        total_length = (main_slice.stop - main_slice.start)
        remainder = total_length % length
        parts = total_length // length

        slices = []
        counter = 0
        for i in range(parts):
            slices.append(slice(counter, counter + length))
            counter += length
        if remainder > 0:
            slices.append(slice(counter, main_slice.stop))
        return slices

    def find_max_its(self):
        """
        Finds maximum iterations needed based on intensity of particles found
        ----------------
        :return: max_its: integer of maximum iterations needed
        """
        # take first frame
        first_frame_index = self.tt_parts[0].slice.start
        first_frame = np.asarray(self.frames[first_frame_index])

        # create temp fitter
        fitter_tmp = GaussianBackground({'roi_size': 7, 'rejection': True, 'method': "Gaussian - Fit bg"},
                                        400, 6, self.roi_offset)
        int_list = []

        # for every ROI, find intensity
        for roi in self.active_rois:
            my_roi = roi.get_roi(first_frame, 3, self.roi_offset)
            result, its, success = fitter_tmp.fit_gaussian(my_roi)
            if result[0] > 0:
                int_list.append(result[0])

        # fit intensity
        mu, std = norm.fit(int_list)
        intensity_list2 = np.asarray(int_list)[int_list < mu]
        if len(intensity_list2) > 0:
            mu, std = norm.fit(intensity_list2)

        # set max its depending on mean intensity
        int_under_which_more_its_are_needed = 3000
        if mu >= int_under_which_more_its_are_needed:
            max_its = 100
        else:
            max_its = np.ceil((int_under_which_more_its_are_needed - mu) / 1000) * 100 + 100

        # final check
        if max_its > 400:
            max_its = 400

        return int(max_its)

    def correlate_tt_parts(self):
        """
        Function to correlate the first frame of each TTPart.
        ----------------------------------------------------
        :return: None. Changes TTPart classes by setting offset_from_base
        """
        last_non_nan_offset = np.asarray([0, 0])
        old_frame = None
        for index, tt_part in enumerate(self.tt_parts):
            if index == 0:
                tt_part.offset_from_base = last_non_nan_offset.copy()
                old_frame = np.asarray(tt_part.frame_zero)
                background = median_filter(old_frame, size=9, mode='constant')
                old_frame = old_frame.astype(self.data_type_signed) - background
            else:
                if tt_part.corr:
                    new_frame = np.asarray(tt_part.frame_zero)
                    background = median_filter(new_frame, size=9, mode='constant')
                    new_frame = new_frame.astype(self.data_type_signed) - background
                    # input roi_size as maximum possible drift
                    last_non_nan_offset += np.asarray(self.correlate_frames_same_size(old_frame, new_frame,
                                                                                      range=self.settings['roi_size']))
                    old_frame = new_frame
                tt_part.offset_from_base = last_non_nan_offset.copy()

    def run(self):
        """
        Run TT analysis. Takes set slice of video, analyses it, and corrects for drift
        :return: None. Edits results in experiment
        """
        if mp.current_process().name == "MainProcess":
            # update time axis
            if self.time_axis_dim == 't':
                self.time_axis = self.metadata['timesteps'][slice(self.tt_parts[0].slice.start,
                                                                  self.tt_parts[-1].slice.stop)]
            else:
                self.time_axis = np.asarray(range(self.tt_parts[0].slice.start, self.tt_parts[-1].slice.stop))

            # find correlation between tt_parts
            self.correlate_tt_parts()
            # run
            if len(self.tt_parts) > 1:
                if self.n_cores > 1:
                    self.tt_parts_done = 0
                    tt_parts_created = 0
                    # created shared dictionaries (these will hold the results) and
                    # the queue (which will get progress updates)
                    dicts_list = []
                    q = mp.SimpleQueue()
                    manager = mp.Manager()

                    while tt_parts_created < len(self.tt_parts):
                        # create processes, each with its own shared_dict to prevent large amount of data to be shared
                        # continue creating while the number of processes running is equal to n_cores
                        while tt_parts_created - self.tt_parts_done < self.n_cores:
                            # break if enough parts created
                            if tt_parts_created == len(self.tt_parts):
                                break
                            shared_dict = manager.dict()
                            _thread.start_new_thread(self.mp_create_process, (self.tt_parts[tt_parts_created],
                                                                              shared_dict, q))
                            dicts_list.append(shared_dict)
                            tt_parts_created += 1

                        # Check progress while not done creating processes yet
                        while tt_parts_created - self.tt_parts_done == self.n_cores:
                            q.get()
                            self.experiment.progress_updater.update_progress()

                    # check progress knowing that they should complete
                    while not self.experiment.progress_updater.dataset_completed:
                        q.get()
                        self.experiment.progress_updater.update_progress()
                else:
                    dicts_list = []
                    for _ in range(len(self.tt_parts)):
                        dicts_list.append({})
                    for index, tt_part in enumerate(self.tt_parts):
                        tt_part.run(self.fitter, self.active_rois, res_dict=dicts_list[index], dataset=self)

                # merge data
                self.experiment.progress_updater.message("Finalizing data")
                self.merge_data(dicts_list)
            else:
                self.tt_parts[0].run(self.fitter, self.active_rois, dataset=self)
                self.experiment.progress_updater.message("Finalizing data")

            # set to nm if desired
            if self.settings['pixels_or_nm'] == "nm":
                for roi in self.active_rois:
                    roi.results[self.name_result]['result'] = change_to_nm(roi.results[self.name_result]['result'],
                                                                           self.metadata, self.settings['method'])

            # add nm or pixels and time axis to result
            for roi in self.active_rois:
                roi.results[self.name_result]['dimension'] = self.settings['pixels_or_nm']
                roi.results[self.name_result]['time_axis'] = self.time_axis
                roi.results[self.name_result]['time_axis_dim'] = self.time_axis_dim

            # correct for drift
            self.experiment.progress_updater.message("Starting drift correction")
            self.drift_corrector = DriftCorrector(self.settings['method'])
            self.drift_corrector.main(self.active_rois, self.name_result, len(self.time_axis))

    def merge_data(self, dicts_list):
        """
        Merges the data in the case that a TT Dataset was split in TTParts
        ----------------------
        :param dicts_list: dictionaries that hold all the individual results of the split TTParts
        -----------------------
        :return: None. Changes the active ROIs by saving the results there.
        """

        for roi in self.active_rois:
            roi_result = np.zeros((self.tt_parts[-1].slice.stop - self.tt_parts[0].frame_start,
                                   dicts_list[0]["{}".format(roi.index)]['result'].shape[1]))
            roi_raw = np.zeros((self.tt_parts[-1].slice.stop - self.tt_parts[0].frame_start,
                                self.fitter.roi_size, self.fitter.roi_size), dtype=self.data_type)
            counter = 0
            for tt_part_dict in dicts_list:
                part_dict = tt_part_dict.pop("{}".format(roi.index), None)
                # no longer within frame, stop
                if part_dict is None:
                    roi_result[counter:-1, :] = np.nan
                    roi_raw[counter:-1, :, :] = np.nan
                    break
                else:
                    roi_result[counter:counter + part_dict["result"].shape[0], :] = part_dict["result"]
                    roi_raw[counter:counter + part_dict["result"].shape[0], :, :] = part_dict["raw"]
                    counter += part_dict["result"].shape[0]

            roi.results[self.name_result] = {"type": 'TT', "result": roi_result, "raw": roi_raw}

    def mp_create_process(self, tt_part, shared_dict, q):
        """
        Called by threads to start a process, monitors it, and joins it at the end
        ----------------------------------------------------
        :param tt_part: The TT part to be fitted by this process
        :param shared_dict: The shared_dictionary of results
        :param q: The queue in which updates will be put
        :return: None. Process changes shared_dict
        """
        p = mp.Process(target=self.run_mp, args=(self.fitter, tt_part, self.active_rois, shared_dict, q))
        p.start()
        p.join()
        self.tt_parts_done += 1

    @staticmethod
    def run_mp(fitter, tt_part, rois, shared_dict, q):
        """
        The run for each individual process for MP. Reloads the nd2 (this takes a while), and fits it
        ----------------------
        :param fitter: The fitter to use to fit
        :param tt_part: The TT part to be fitted by this process
        :param rois: The rois to fit
        :param shared_dict: The shared dictionary to place the results in
        :param q: The queue to place updates in
        :return: None, changes the shared_dict
        """
        # load in slice of video
        full_frame_stack = np.asarray(ND2ReaderSelf(tt_part.name)[tt_part.slice])
        # create frame stacks of each ROIs
        frame_stacks = []
        total_offset = fitter.roi_offset + tt_part.offset_from_base
        for roi in rois:
            if roi.in_frame(full_frame_stack[0].shape, total_offset, fitter.roi_size_1D):
                frame_stacks.append(roi.get_frame_stack(full_frame_stack, fitter.roi_size_1D, total_offset))
            else:
                # if not in frame, append a None to ensure same length
                frame_stacks.append(None)
        # delete full frame from memory
        del full_frame_stack
        # run
        fitter.run(frame_stacks, rois, tt_part, q=q, res_dict=shared_dict)

# %% TT Part


class TTPart:
    """
    Class that holds a part of a TT Dataset, and the offset of that part to the beginning.
    Used when datasets are too large for memory, multiprocessing or when drift-correction during experiment is desired
    """
    def __init__(self, name, nd2, video_slice, corr=True):
        """
        Initialisation of TTPart. Takes start info
        ----------------------------
        :param name: name of nd2
        :param nd2: actual nd2 to be used to get frame_zero from for correlation
        :param video_slice: slice of the video for this part
        :param corr: Whether or not correlation should be done on this TTPart. Only False for MP created TTParts
        """
        self.name = name
        self.slice = video_slice
        self.frame_start = video_slice.start
        self.frame_zero = np.asarray(nd2[self.frame_start])
        self.corr = corr
        self.offset_from_base = [0, 0]

    def run(self, fitter, rois, res_dict=None, dataset=None):
        """
        The run for each individual process for single process. Takes the slice of the ND2 and fits it
        ----------------------
        :param fitter: The fitter to use to fit
        :param rois: The rois to fit
        :param res_dict: The result dictionary to place the results in, only used if more than one TTPart
        :param dataset: Information of the dataset. Used when single process used.
        :return: None. Changes the res_dict or the ROIs
        """
        # load in slice of video
        full_frame_stack = np.asarray(ND2ReaderSelf(self.name)[self.slice])
        # create frame stacks of each ROIs
        frame_stacks = []
        total_offset = fitter.roi_offset + self.offset_from_base
        for roi in rois:
            if roi.in_frame(full_frame_stack[0].shape, total_offset, fitter.roi_size_1D):
                frame_stacks.append(roi.get_frame_stack(full_frame_stack, fitter.roi_size_1D, total_offset))
            else:
                # if not in frame, append a None to ensure same length
                frame_stacks.append(None)
        # delete full frame from memory
        del full_frame_stack
        # run
        fitter.run(frame_stacks, rois, self, res_dict=res_dict, dataset=dataset)

# %% Base Run


class BaseFitter:
    """
    Base fitter class. Used by all other fitters.
    """
    def __init__(self, settings, roi_offset):
        self.roi_size = settings['roi_size']
        self.roi_size_1D = int((self.roi_size - 1) / 2)
        self.__name__ = settings['method']
        self.rejection = settings['rejection']

        self.roi_offset = roi_offset

    def fitter(self, frame_stack, roi_index, y, x, tt_part):
        """
        To be implemented depending on fitter
        :param frame_stack: frame stack to be fitted of a single ROI
        :param roi_index: the ROIs index
        :param y: y-position of ROI center
        :param x: x-position of ROI center
        :param tt_part: information about which part of the TT is being fitted
        :return: roi results
        """
        pass

    def run(self, frame_stacks, rois, tt_part, dataset=None, q=None, res_dict=None):
        """
        Run of fitter. Takes ROIs and fits them all. Return results.
        In case of MP, q and res_dict are given, and the results wil be placed in there.
        -------------------------------
        :param frame_stacks: Frame stacks to fit
        :param rois: ROIs to fit
        :param tt_part: information about which part of the TT is being fitted
        :param dataset: The dataset to fit. Only used when single core is used
        :param q: Queue to place updates in when MP is used. Each time a ROI is finished, 1 is placed in it
        :param res_dict: The shared dictionary to save results to. Only used for MP
        :return: None. Edits dataset
        """
        if res_dict is not None:
            res_dict["start_frame"] = tt_part.frame_start

        for frame_stack, roi in zip(frame_stacks, rois):
            if frame_stack is not None:
                roi_result = self.fitter(frame_stack, roi.index, roi.y, roi.x, tt_part)
                result_dict = {"type": 'TT', "result": roi_result, "raw": frame_stack}

                # else triggered when split dataset in parts
                if res_dict is None:
                    roi.results[dataset.name_result] = result_dict
                else:
                    res_dict["{}".format(roi.index)] = result_dict

            # regardless of frame_stack None or not, send update
            if dataset is not None:
                dataset.experiment.progress_updater.update_progress()
            else:
                q.put(1)

# %% Gaussian fitter with estimated background


TERMINATION_MESSAGES = {
    -1: "Improper input parameters status returned from `leastsq`",
    0: "The maximum number of function evaluations is exceeded.",
    1: "`gtol` termination condition is satisfied.",
    2: "`ftol` termination condition is satisfied.",
    3: "`xtol` termination condition is satisfied.",
    4: "Both `ftol` and `xtol` termination conditions are satisfied."
}

FROM_MINPACK_TO_COMMON = {
    0: -1,  # Improper input parameters from MINPACK.
    1: 2,
    2: 3,
    3: 4,
    4: 1,
    5: 0
    # There are 6, 7, 8 for too small tolerance parameters,
    # but we guard against it by checking ftol, xtol, gtol beforehand.
}

EPS = np.finfo(float).eps


# noinspection DuplicatedCode
class Gaussian(BaseFitter):
    """
    Gaussian fitter with estimated background, build upon Scipy Optimize Least-Squares
    """
    def __init__(self, settings, max_its, num_fit_params, roi_offset):
        """
        Initializer of Gaussian fitter. Sets a lot of base values
        ----------
        :param settings: Fitting settings
        :param: max_its: number of iterations limit
        :param num_fit_params: number of fitting parameters, 5 for without bg, 6 with bg
        :param roi_offset: offset of ROIs in dataset
        """
        super().__init__(settings, roi_offset)

        self.init_sig = 1.2  # Slightly on the high side probably
        self.num_fit_params = num_fit_params
        self.params = np.zeros(2)

        self.x_scale = np.ones(num_fit_params)
        self.active_mask = np.zeros_like(self.x_scale, dtype=int)

        self.lb = np.resize(-np.inf, self.x_scale.shape)
        self.ub = np.resize(np.inf, self.x_scale.shape)
        self.use_one_sided = np.resize(False, self.x_scale.shape)

        self.rel_step = EPS ** (1 / 3)
        self.comp = np.ones(num_fit_params)

        self.max_its = max_its

    def fun_find_max(self, roi):
        """
        Input ROI, returns max using FORTRAN

        Parameters
        ----------
        roi : region of interest

        Returns
        -------
        maximum

        """
        if self.roi_size == 9:
            return fortran_tools.max9(roi)
        elif self.roi_size == 7:
            return fortran_tools.max7(roi)

    def fun_find_min(self, roi):
        """
        Input ROI, returns minimum using FORTRAN

        Parameters
        ----------
        roi : region of interest

        Returns
        -------
        minimum

        """
        if self.roi_size == 9:
            return fortran_tools.min9(roi)
        elif self.roi_size == 7:
            return fortran_tools.min7(roi)

    def fun_calc_bg(self, roi):
        """
        Input ROI, returns background using FORTRAN

        Parameters
        ----------
        roi : region of interest

        Returns
        -------
        background

        """
        if self.roi_size == 9:
            return fortran_tools.calc_bg9(roi)
        elif self.roi_size == 7:
            return fortran_tools.calc_bg7(roi)

    def fun_norm(self, g):
        """
        Input 5 or 6 long array, returns norm using FORTRAN

        Parameters
        ----------
        g : vector of norm is to be found

        Returns
        -------
        norm of g

        """
        if self.num_fit_params == 5:
            return fortran_tools.norm5(g)
        elif self.num_fit_params == 6:
            return fortran_tools.norm6(g)

    def fun_gaussian(self, x, data):
        """
        Creates a gaussian with parameters x, returns difference between that and data using FORTRAN

        Parameters
        ----------
        x : Parameters of Gaussian
        data : ROI pixel values to be subtracted from created Gaussian

        Returns
        -------
        Difference between created 2D Gaussian and data

        """
        if self.num_fit_params == 5 and self.roi_size == 9:
            return fortran_linalg.gaussian(*x, self.roi_size, data)
        elif self.num_fit_params == 5 and self.roi_size == 7:
            return fortran_linalg.gaussian7(*x, self.roi_size, data)
        elif self.num_fit_params == 6 and self.roi_size == 9:
            return fortran_linalg.gs_bg(*x, self.roi_size, data)
        elif self.num_fit_params == 6 and self.roi_size == 7:
            return fortran_linalg.gs_bg7(*x, self.roi_size, data)

    def fun_jacobian(self, x0, data):
        """
        Generated jacobian using FORTRAN

        Parameters
        ----------
        x0 : Parameters of Gaussian
        data : ROI pixel values to be subtracted from created Gaussian

        Returns
        -------
        Jacobian

        """
        if self.num_fit_params == 5 and self.roi_size == 9:
            return fortran_linalg.dense_dif(x0, self.rel_step, self.comp,
                                            self.num_fit_params, self.roi_size, data)
        elif self.num_fit_params == 5 and self.roi_size == 7:
            return fortran_linalg.dense_dif7(x0, self.rel_step, self.comp,
                                             self.num_fit_params, self.roi_size, data)
        elif self.num_fit_params == 6 and self.roi_size == 9:
            return fortran_linalg.dense_dif_bg(x0, self.rel_step, self.comp,
                                               self.num_fit_params, self.roi_size, data)
        elif self.num_fit_params == 6 and self.roi_size == 7:
            return fortran_linalg.dense_dif_bg7(x0, self.rel_step, self.comp,
                                                self.num_fit_params, self.roi_size, data)

    def call_minpack(self, fun, x0, data, ftol, xtol, gtol, max_nfev, diag):
        """
        Caller of minpack, which is the iterative method of Python

        Parameters
        ----------
        fun : Function to be fitted
        x0 : Parameters
        data : Data to be compared to
        ftol : function tolerance
        xtol : parameter tolerance
        gtol : gradient tolerance
        max_nfev : max iterations
        diag : diagonal

        Returns
        -------
        Iterated result

        """
        n = x0.size
        epsfcn = EPS

        full_output = True
        factor = 100.0

        if max_nfev is None:
            # n squared to account for Jacobian evaluations.
            max_nfev = 100 * n * (n + 1)
        x, info, status = _minpack._lmdif(
            fun, x0, (), full_output, ftol, xtol, gtol,
            max_nfev, epsfcn, factor, diag)

        f = info['fvec']

        j = self.fun_jacobian(x0, data)

        cost = 0.5 * np.dot(f, f)
        g = j.T.dot(f)
        g_norm = self.fun_norm(g)

        nfev = info['nfev']
        njev = info.get('njev', None)

        status = FROM_MINPACK_TO_COMMON[status]
        active_mask = self.active_mask

        return OptimizeResult(
            x=x, cost=cost, fun=f, jac=j, grad=g, optimality=g_norm,
            active_mask=active_mask, nfev=nfev, njev=njev, status=status)

    def least_squares(self, x0, data, ftol=1e-8, xtol=1e-8, gtol=1e-8,
                      max_nfev=None):
        """
        The least-squares iterator. Does preparation before minpack iterator is called

        Parameters
        ----------
        x0 : parameters to be fitted
        data : data to be fitter to
        ftol : optional function tolerance. The default is 1e-8.
        xtol : optional parameter tolerance. The default is 1e-8.
        gtol : optional gradient tolerance. The default is 1e-8.
        max_nfev : optional max iterations. The default is None.

        Raises
        ------
        ValueError: in case you did anything wrong, should not happen if you just input a 2D Gaussian

        Returns
        -------
        Iterated result

        """

        def fun_wrapped(x):

            return self.fun_gaussian(x, data)

        if max_nfev is not None and max_nfev <= 0:
            raise ValueError("`max_nfev` must be None or positive integer.")

        if np.iscomplexobj(x0):
            raise ValueError("`x0` must be real.")

        if x0.ndim > 1:
            raise ValueError("`x0` must have at most 1 dimension.")

        f0 = fun_wrapped(x0)

        if f0.ndim != 1:
            raise ValueError("`fun` must return at most 1-d array_like.")

        result = self.call_minpack(fun_wrapped, x0, data, ftol, xtol, gtol,
                                   max_nfev, self.x_scale)

        result.message = TERMINATION_MESSAGES[result.status]
        result.success = result.status > 0

        return result

    def phasor_fit(self, data):
        """
        Does Phasor fit to estimate parameters using FORTRAN

        Parameters
        ----------
        data : ROI pixel values

        Returns
        -------
        pos_x : position in x-direction in ROI
        pos_y : position in y-direction in ROI

        """
        if self.roi_size == 9:
            x_re, x_im, y_re, y_im = fortran_tools.fft9(data)
        else:
            x_re, x_im, y_re, y_im = fortran_tools.fft7(data)

        roi_size = self.roi_size
        ang_x = atan2(x_im, x_re)
        if ang_x > 0:
            ang_x = ang_x - 2 * pi

        pos_x = abs(ang_x) / (2 * pi / roi_size) - 1

        ang_y = atan2(y_im, y_re)

        if ang_y > 0:
            ang_y = ang_y - 2 * pi

        pos_y = abs(ang_y) / (2 * pi / roi_size) - 1

        return pos_x, pos_y

    def phasor_guess(self, data):
        """
        Returns an initial guess based on phasor fitting

        Parameters
        ----------
        data : ROI pixel values

        Returns
        -------
        Parameters for Gaussian fitting. In order: height, position y, position x, y-sigma, x-sigma.

        """
        pos_x, pos_y = self.phasor_fit(data)
        height = data[int(pos_y), int(pos_x)] - self.fun_find_min(data)

        return np.array([height, pos_y, pos_x, self.init_sig, self.init_sig])

    def fit_gaussian(self, data):
        """
        Gathers parameter estimate and calls fit.

        Parameters
        ----------
        data : ROI pixel values

        Returns
        -------
        p.x: solution of parameters
        p.nfev: number of iterations
        p.success: success or failure

        """
        if self.params[0] == 0:
            params = self.phasor_guess(data)
        else:
            params = self.phasor_guess(data)
            params[3:5] = self.params[:]
        p = self.least_squares(params, data, max_nfev=self.max_its)  # , ftol=1e-10, xtol=1e-10, gtol=1e-10)

        return [p.x, p.nfev, p.success]

    def define_fitter_bounds(self):
        """
        Defines fitter bounds, based on "Strict" bounds or not

        Returns
        -------
        pos_max : Max position of fit
        pos_min : Min position of fit
        int_max : Max intensity of fit
        int_min : Min intensity of fit
        sig_max : Max sigma of fit
        sig_min : Min sigma of fit

        """
        pos_max = self.roi_size
        pos_min = 0
        int_min = 0
        int_max = ((2 ** 16) - 1) * 1.5  # 50% margin over maximum pixel value possible
        sig_min = 0
        sig_max = self.roi_size_1D + 1

        return pos_max, pos_min, int_max, int_min, sig_max, sig_min

    def fitter(self, frame_stack, roi_index, y, x, tt_part):
        """
        Does Gaussian fitting for all frames for a single ROI
        --------------------------------------------------------
        :param frame_stack: frame stack to be fitted of single ROI
        :param roi_index: the ROIs index
        :param y: y-position of ROI center
        :param x: x-position of ROI center
        :param tt_part: information about which part of the TT is being fitted
        :return: roi results
        """
        pos_max, pos_min, int_max, int_min, sig_max, sig_min = self.define_fitter_bounds()

        self.params = np.zeros(2)
        roi_result = np.zeros([frame_stack.shape[0], 8])

        for frame_index, my_roi in enumerate(frame_stack):
            my_roi_bg = self.fun_calc_bg(my_roi)
            my_roi = my_roi - my_roi_bg
            result, its, success = self.fit_gaussian(my_roi)

            if self.rejection is False:
                if success == 0 or result[0] == 0:
                    self.params = [self.init_sig, self.init_sig]
                    success = 0
            else:
                if success == 0 or \
                        result[2] < pos_min or result[2] > pos_max or result[1] < pos_min or result[1] > pos_max or \
                        result[0] <= int_min or result[0] > int_max or \
                        result[3] < sig_min or result[3] > sig_max or result[4] < sig_min or result[4] > sig_max:
                    self.params = [self.init_sig, self.init_sig]
                    success = 0

            if success == 1:
                self.params = result[3:5]
                roi_result[frame_index, 0] = frame_index + tt_part.frame_start
                # start position plus from center in ROI + half for indexing of pixels
                roi_result[frame_index, 1] = result[1] + y - self.roi_size_1D + 0.5 + tt_part.offset_from_base[0]  # y
                roi_result[frame_index, 2] = result[2] + x - self.roi_size_1D + 0.5 + tt_part.offset_from_base[1]  # x
                roi_result[frame_index, 3] = result[0]*result[3]*result[4]*2*pi  # Integrated intensity
                roi_result[frame_index, 4] = result[3]  # sigma y
                roi_result[frame_index, 5] = result[4]  # sigma x
                roi_result[frame_index, 6] = my_roi_bg
                roi_result[frame_index, 7] = its
            else:
                roi_result[frame_index, :] = np.nan
                roi_result[frame_index, 0] = frame_index + tt_part.frame_start

        return roi_result

# %% Gaussian fitter including background


# noinspection DuplicatedCode
class GaussianBackground(Gaussian):
    """
    Gaussian fitter with fitted background, build upon Scipy Optimize Least-Squares
    """
    def phasor_guess(self, data):
        """
        Returns an initial guess based on phasor fitting

        Parameters
        ----------
        data : ROI pixel values

        Returns
        -------
        Parameters for Gaussian fitting. In order: height, position y, position x, y-sigma, x-sigma, background.

        """
        pos_x, pos_y = self.phasor_fit(data)
        background = self.fun_calc_bg(data)
        height = data[int(pos_y), int(pos_x)] - background

        return np.array([height, pos_y, pos_x, self.init_sig, self.init_sig, background])

    def fitter(self, frame_stack, roi_index, y, x, tt_part):
        """
        Does Gaussian fitting for all frames for a single ROI
        --------------------------------------------------------
        :param frame_stack: frame stack to be fitted of single ROI
        :param roi_index: the ROIs index
        :param y: y-position of ROI center
        :param x: x-position of ROI center
        :param tt_part: information about which part of the TT is being fitted
        :return: roi results
        """
        pos_max, pos_min, int_max, int_min, sig_max, sig_min = self.define_fitter_bounds()
        self.params = np.zeros(2)
        roi_result = np.zeros([frame_stack.shape[0], 8])

        for frame_index, my_roi in enumerate(frame_stack):
            result, its, success = self.fit_gaussian(my_roi)

            if self.rejection is False:
                if success == 0 or result[0] == 0:
                    self.params = [self.init_sig, self.init_sig]
                    success = 0
            else:
                if success == 0 or \
                        result[2] < pos_min or result[2] > pos_max or result[1] < pos_min or result[1] > pos_max or \
                        result[0] <= int_min or result[0] > int_max or \
                        result[3] < sig_min or result[3] > sig_max or result[4] < sig_min or result[4] > sig_max:
                    self.params = [self.init_sig, self.init_sig]
                    success = 0

            if success == 1:
                self.params = result[3:5]

                roi_result[frame_index, 0] = frame_index + tt_part.frame_start
                # start position plus from center in ROI + half for indexing of pixels
                roi_result[frame_index, 1] = result[1] + y - self.roi_size_1D + 0.5 + tt_part.offset_from_base[0]  # y
                roi_result[frame_index, 2] = result[2] + x - self.roi_size_1D + 0.5 + tt_part.offset_from_base[1]  # x
                roi_result[frame_index, 3] = result[0] * result[3] * result[4] * 2 * pi  # Integrated intensity
                roi_result[frame_index, 4] = result[3]  # sigma y
                roi_result[frame_index, 5] = result[4]  # sigma x
                roi_result[frame_index, 6] = result[5]  # background
                roi_result[frame_index, 7] = its
            else:
                roi_result[frame_index, :] = np.nan
                roi_result[frame_index, 0] = frame_index

        return roi_result

# %% Phasor for ROI loops


class Phasor(BaseFitter):
    """
    Phasor fitting using Fourier Transform. Also returns intensity of pixel in which Phasor position is found.
    """
    def fun_find_max(self, roi):
        """
        Input ROI, returns max using FORTRAN

        Parameters
        ----------
        roi : region of interest

        Returns
        -------
        maximum

        """
        if self.roi_size == 9:
            return fortran_tools.max9(roi)
        elif self.roi_size == 7:
            return fortran_tools.max7(roi)

    def fun_calc_bg(self, roi):
        """
        Input ROI, returns background using FORTRAN

        Parameters
        ----------
        roi : region of interest

        Returns
        -------
        background

        """
        if self.roi_size == 9:
            return fortran_tools.calc_bg9(roi)
        elif self.roi_size == 7:
            return fortran_tools.calc_bg7(roi)

    def fft_to_pos(self, fft_values):
        """
        Convert the found Fourier transform to a Phasor position

        Parameters
        ----------
        fft_values : Fourier transform of ROI

        Returns
        -------
        pos_x : x-position of Phasor
        pos_y : y-position of Phasor

        """
        ang_x = phase(fft_values[0, 1])
        if ang_x > 0:
            ang_x = ang_x - 2 * pi

        pos_x = abs(ang_x) / (2 * pi / self.roi_size) + 0.5

        ang_y = phase(fft_values[1, 0])

        if ang_y > 0:
            ang_y = ang_y - 2 * pi

        pos_y = abs(ang_y) / (2 * pi / self.roi_size) + 0.5

        return pos_x, pos_y

    def get_fft_values(self, frame_stack):
        """
        Converts frame stack to fft values
        -----------------------
        :param frame_stack: frame stack to convert
        :return: fft_values: fft of frame_stack
        """
        roi_bb = empty_aligned(frame_stack.shape, dtype='float64')
        roi_bf = empty_aligned((frame_stack.shape[0], self.roi_size, self.roi_size_1D + 1), dtype='complex128')
        fft_values_list = FFTW(roi_bb, roi_bf, axes=(1, 2),
                               flags=('FFTW_MEASURE',),
                               direction='FFTW_FORWARD')
        roi_bb = frame_stack
        return fft_values_list(roi_bb)

    def fit_and_reject(self, fft_values):
        """
        Takes fft values, fits and rejects if need be
        ------------------------
        :param fft_values: values to fit
        :return: pos_x: x pos found
        :return: pos_y: y pos found
        :return: success: if fit was success
        """
        success = 1
        pos_x, pos_y = self.fft_to_pos(fft_values)

        if self.rejection is True and (pos_x > self.roi_size or pos_x < 0):
            success = 0
        if self.rejection is True and (pos_y > self.roi_size or pos_y < 0):
            success = 0

        return pos_x, pos_y, success

    def fitter(self, frame_stack, roi_index, y, x, tt_part):
        """
        Applies phasor fitting to an entire stack of frames of one ROI

        Parameters
        ----------
        frame_stack : stack of frames of a single ROI
        roi_index : Index of ROI that is currently being fitted
        y : y-location with respect to total microscope frame of currently fitted ROI
        x : x-location with respect to total microscope frame of currently fitted ROI
        tt_part: information about which part of the TT is being fitted

        Returns
        -------
        roi_result : Result of all the frames of the current ROI

        """
        roi_result = np.zeros([frame_stack.shape[0], 5])
        fft_values_list = self.get_fft_values(frame_stack)

        for frame_index, (fft_values, frame) in enumerate(zip(fft_values_list, frame_stack)):
            my_frame_bg = self.fun_calc_bg(frame)
            frame_max = self.fun_find_max(frame)

            pos_x, pos_y, success = self.fit_and_reject(fft_values)
            if frame_max == 0:
                success = 0

            if success == 1:
                roi_result[frame_index, 0] = frame_index + tt_part.frame_start
                # start position plus from center in ROI + half for indexing of pixels
                roi_result[frame_index, 1] = y + pos_y - self.roi_size_1D + tt_part.offset_from_base[0]  # y
                roi_result[frame_index, 2] = x + pos_x - self.roi_size_1D + tt_part.offset_from_base[1]  # x
                roi_result[frame_index, 3] = frame_max - my_frame_bg  # returns max peak
                roi_result[frame_index, 4] = my_frame_bg  # background
            else:
                roi_result[frame_index, :] = np.nan
                roi_result[frame_index, 0] = frame_index + tt_part.frame_start

        return roi_result

# %% Dumb phasor ROI loop


class PhasorDumb(Phasor):
    """
    Dumb Phasor. Does not return intensity of found location.
    """
    def fitter(self, frame_stack, roi_index, y, x, tt_part):
        """
        Applies phasor fitting to an entire stack of frames of one ROI

        Parameters
        ----------
        frame_stack : stack of frames of a single ROI
        roi_index : Index of ROI that is currently being fitted
        y : y-location with respect to total microscope frame of currently fitted ROI
        x : x-location with respect to total microscope frame of currently fitted ROI
        tt_part: information about which part of the TT is being fitted

        Returns
        -------
        roi_result : Result of all the frames of the current ROI

        """
        roi_result = np.zeros([frame_stack.shape[0], 3])
        fft_values_list = self.get_fft_values(frame_stack)

        for frame_index, (fft_values, frame) in enumerate(zip(fft_values_list, frame_stack)):
            pos_x, pos_y, success = self.fit_and_reject(fft_values)

            if success == 1:
                roi_result[frame_index, 0] = frame_index + tt_part.frame_start
                # start position plus from center in ROI + half for indexing of pixels
                roi_result[frame_index, 1] = y + pos_y - self.roi_size_1D + tt_part.offset_from_base[0]  # y
                roi_result[frame_index, 2] = x + pos_x - self.roi_size_1D + tt_part.offset_from_base[1]  # x
            else:
                roi_result[frame_index, :] = np.nan
                roi_result[frame_index, 0] = frame_index + tt_part.frame_start

        return roi_result

# %% Phasor with sum


class PhasorSum(Phasor):
    """
    Phasor Sum. Also returns summation of entire ROI
    """
    def fitter(self, frame_stack, roi_index, y, x, tt_part):
        """
        Applies phasor fitting to an entire stack of frames of one ROI

        Parameters
        ----------
        frame_stack : stack of frames of a single ROI
        roi_index : Index of ROI that is currently being fitted
        y : y-location with respect to total microscope frame of currently fitted ROI
        x : x-location with respect to total microscope frame of currently fitted ROI
        tt_part: information about which part of the TT is being fitted

        Returns
        -------
        roi_result : Result of all the frames of the current ROI

        """
        roi_result = np.zeros([frame_stack.shape[0], 4])
        fft_values_list = self.get_fft_values(frame_stack)

        for frame_index, (fft_values, frame) in enumerate(zip(fft_values_list, frame_stack)):
            frame_sum = np.sum(frame)
            pos_x, pos_y, success = self.fit_and_reject(fft_values)
            if frame_sum == 0:
                success = 0

            if success == 1:
                roi_result[frame_index, 0] = frame_index + tt_part.frame_start
                # start position plus from center in ROI + half for indexing of pixels
                roi_result[frame_index, 1] = y + pos_y - self.roi_size_1D + tt_part.offset_from_base[0]  # y
                roi_result[frame_index, 2] = x + pos_x - self.roi_size_1D + tt_part.offset_from_base[1]  # x
                roi_result[frame_index, 3] = frame_sum  # returns summation
            else:
                roi_result[frame_index, :] = np.nan
                roi_result[frame_index, 0] = frame_index + tt_part.frame_start

        return roi_result
