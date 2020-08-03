# -*- coding: utf-8 -*-
"""
Created on Thu 30-07-2020

@author: Dion Engels
MBx Python Data Analysis

drift_correction

This package is for the drift correction of MBx Python.

----------------------------

v0.1: drift correction v1: 31/07/2020

"""

import numpy as np
from scipy.stats import norm


class DriftCorrector:
    """
    Drift correction class of MBx Python. Takes results and corrects them for drift
    """
    def __init__(self, method):
        """
        Initialisation, does not do much
        """
        self.threshold_sigma = 5
        self.method = method
        self.n_rois = 0
        self.n_frames = 0

    def main(self, results, rois, n_frames):
        """
        Main, put in results and get out drift corrected results

        Parameters
        ----------
        results: non-drift corrected results
        rois: list of ROIs
        n_frames: number of frames fitted

        Returns
        ----------
        results_drift: drift corrected results
        """
        np.warnings.filterwarnings('ignore')  # ignore warnings of "nan" values to a real value

        self.n_rois = rois.shape[0]
        self.n_frames = n_frames

        all_drift_x = np.zeros((self.n_frames, self.n_rois))
        all_drift_y = np.zeros((self.n_frames, self.n_rois))

        for i in range(1, self.n_rois+1):  # find drift per ROI
            roi_results = results[results[:, 1] == i, :]
            roi_drift_x, roi_drift_y = self.find_drift(roi_results)
            all_drift_x[:, i-1] = roi_drift_x  # -1 since converted to MATLAB counting
            all_drift_y[:, i-1] = roi_drift_y  # -1 since converted to MATLAB counting
        mean_drift_x = np.nanmean(all_drift_x, axis=1)  # average drift of all ROIs
        mean_drift_y = np.nanmean(all_drift_y, axis=1)  # average drift of all ROIs

        return self.adjust_for_drift(mean_drift_x, mean_drift_y, results)

    def find_drift(self, roi_results):

        if self.method == "Gaussian" or self.method == "GaussianBackground" \
                or self.method == "Gaussian - Fit bg" or self.method == "Gaussian - Estimate bg":
            cutoff = self.find_cutoff(roi_results)
            roi_results[roi_results[:, 4] > cutoff, 2:] = np.nan

        roi_drift_x = roi_results[:, 2] - roi_results[0, 2]
        roi_drift_y = roi_results[:, 3] - roi_results[0, 3]

        return roi_drift_x, roi_drift_y

    def find_cutoff(self, roi_results):
        int_ravel = roi_results[~np.isnan(roi_results[:, 4]), 4]
        mean = 0
        std = 0

        for _ in range(10):
            mean, std = norm.fit(int_ravel)
            int_ravel = int_ravel[int_ravel < mean + std * self.threshold_sigma]

        return mean + self.threshold_sigma * std

    def adjust_for_drift(self, mean_drift_x, mean_drift_y, results_drift):

        mean_drift_x_repeat = np.repeat(mean_drift_x, self.n_rois)
        mean_drift_y_repeat = np.repeat(mean_drift_y, self.n_rois)

        results_drift[:, 2] -= mean_drift_x_repeat
        results_drift[:, 3] -= mean_drift_y_repeat

        return results_drift