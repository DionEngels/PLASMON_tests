# -*- coding: utf-8 -*-
"""
Created on Sat Jul 11 19:14:16 2020

@author: Dion Engels
MBx Python Data Analysis

main_GUI

This package is for the GUI of Mbx Python.

----------------------------

v1.0: roll-out version one
v1.1: Bugfixes and improved figures (WIP)
v1.2: GUI and output improvement based on Sjoerd's feedback, HSM: 27/08/2020 - 13/09/2020
v1.3: HSM to eV: 24/09/2020
v1.4: HSM output back to nm, while fitting in eV: 29/09/2020
"""
__version__ = "2.0"
__self_made__ = True

# GENERAL IMPORTS
from os import getcwd, mkdir, environ, listdir  # to get standard usage
from tempfile import mkdtemp
import sys
import time  # for timekeeping
from win32api import GetSystemMetrics  # Get sys info
import warnings  # for warning diversion

environ['MPLCONFIGDIR'] = mkdtemp()

# Numpy and matplotlib, for linear algebra and plotting respectively
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import matplotlib.patches as patches
from scipy.io import loadmat
from scipy.ndimage import median_filter

# GUI
import tkinter as tk  # for GUI
from tkinter import ttk  # GUI styling
from tkinter.filedialog import askopenfilename, askdirectory  # for popup that asks to select .nd2's or folders

# Own code v2
from main import DivertError, ProgressUpdater
from src.class_experiment import Experiment
import src.figure_making as figuring
from src.warnings import InputWarning

# Multiprocessing
import multiprocessing as mp

mpl.use("TkAgg")  # set back end to TK

# %% Initializations. Defining filetypes, fonts, paddings, input sizes, and GUI sizes.

FILETYPES = [("ND2", ".nd2")]
FILETYPES_LOAD_FROM_OTHER = [(".npy and .mat", ".npy"), (".npy and .mat", ".mat")]

FONT_HEADER = "Verdana 14 bold"
FONT_SUBHEADER = "Verdana 11 bold"
FONT_STATUS = "Verdana 12"
FONT_BUTTON = "Verdana 9"
FONT_LABEL = "Verdana 10"
FONT_DROP = "Verdana 10"
FONT_BUTTON_BIG = "Verdana 20"
PAD_BIG = 30
PAD_SMALL = 10
INPUT_BIG = 25
INPUT_SMALL = 5

width = GetSystemMetrics(0)
height = GetSystemMetrics(1)
GUI_WIDTH = 1344  # int(width * 0.70)
GUI_HEIGHT = 756  # int(height * 0.70)
GUI_WIDTH_START = int((width - GUI_WIDTH) / 2)
GUI_HEIGHT_START = int((height - GUI_HEIGHT) / 2)
DPI = 100

# %% Options for dropdown menus

fit_options = ["Gaussian - Fit bg", "Gaussian - Estimate bg",
               "Phasor + Intensity", "Phasor + Sum", "Phasor"]

rejection_options = ["Loose", "None"]

roi_size_options = ["7x7", "9x9"]


# %% Multiprocessing main

# TO DO

# %% Proceed Question

def proceed_question(title, text):
    check = tk.messagebox.askokcancel(title, text)
    return check

# %% Divert errors


class DivertorErrorsGUI(DivertError):
    @staticmethod
    def show(error, traceback_details):
        if error:
            tk.messagebox.showerror("Critical error. Send screenshot to Dion. PROGRAM WILL STOP",
                                    message=str(traceback_details))
        else:
            tk.messagebox.showerror("Warning. Take note. PROGRAM WILL CONTINUE",
                                    message=str(traceback_details))

# %% Close GUI


def quit_gui(gui):
    gui.quit()
    sys.exit(0)

# %% Own buttons / fields


class BigButton(ttk.Frame):
    """
    Big button, used for FIT and LOAD
    """

    def __init__(self, parent, height=None, width=None, text="", command=None, state='enabled'):
        ttk.Frame.__init__(self, parent, height=height, width=width)

        self.pack_propagate(0)
        self._btn = ttk.Button(self, text=text, command=command, state=state)
        self._btn.pack(fill=tk.BOTH, expand=1)
        self._btn["style"] = "Big.TButton"

    def updater(self, state='enabled'):
        self._btn['state'] = state


class FigureFrame(tk.Frame):
    """
    Frame in which Figure sits.
    """
    def __init__(self, parent, height=None, width=None, dpi=DPI):
        tk.Frame.__init__(self, parent, height=height + 40, width=width,
                          highlightbackground="black", highlightthickness=2)

        self.pack_propagate(0)
        self.fig = Figure(figsize=(height / dpi, width / dpi), dpi=dpi)

        self.parent = parent
        self.dpi = dpi
        self.width = width
        self.height = height

        self.canvas = FigureCanvasTkAgg(self.fig, self)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=1)

        self.toolbar = NavigationToolbar2Tk(self.canvas, self)
        self.toolbar.update()
        self.toolbar.configure(background="White")

    def updater(self, frame, roi_locations=None, roi_size=None, roi_offset=None):
        """
        Updater. Takes existing frame with figure and places new figure in it

        Parameters
        ----------
        frame : New frame to be shown
        roi_locations : optional, possible ROI locations to be highlighted. The default is None.
        roi_size : optional, ROI size in case ROIs are highlighted. The default is None.
        roi_offset: offset compared to ROI frame

        Returns
        -------
        Updated figure.

        """
        if roi_offset is None:
            roi_offset = [0, 0]
        self.fig.clear()
        fig_sub = self.fig.add_subplot(111)
        figuring.plot_rois(fig_sub, frame, roi_locations, roi_size, roi_offset)
        self.canvas.draw()
        self.toolbar.update()


class EntryPlaceholder(ttk.Entry):
    """
    Entry with a placeholder text in grey
    """

    def __init__(self, master=None, placeholder="PLACEHOLDER", *args, **kwargs):
        super().__init__(master, *args, style="Placeholder.TEntry", **kwargs)
        self.placeholder = placeholder

        self.insert("0", self.placeholder)
        self.bind("<FocusIn>", self._clear_placeholder)
        self.bind("<FocusOut>", self._add_placeholder)

    def _clear_placeholder(self, e):
        self.delete("0", "end")
        if self["style"] == "Placeholder.TEntry":
            self["style"] = "TEntry"

    def _add_placeholder(self, e):
        if not self.get():
            self.insert("0", self.placeholder)
            self["style"] = "Placeholder.TEntry"

    def updater(self, text=None, placeholder=None):
        self.delete("0", "end")
        if placeholder is not None:
            self.placeholder = placeholder

        if text is None:
            self.insert("0", self.placeholder)
            self["style"] = "Placeholder.TEntry"
        else:
            self.insert("0", text)
            self["style"] = "TEntry"


class NormalButton:
    """
    My normal button, again with an updater function to update the button.
    Only buttons that need updating use this class
    """

    def __init__(self, parent, text=None, row=None, column=None,
                 rowspan=1, columnspan=1, command=None, state='enabled', sticky=None, padx=0, pady=0):
        self._btn = ttk.Button(parent, text=text, command=command, state=state)
        self.parent = parent
        self.text = text
        self.row = row
        self.column = column
        self.rowspan = rowspan
        self.columnspan = columnspan
        self.sticky = sticky
        self.padx = padx
        self.pady = pady
        self._btn.grid(row=row, column=column, rowspan=rowspan, columnspan=columnspan,
                       sticky=sticky, padx=padx, pady=pady)

    def updater(self, command=None, state='enabled', text=None):
        if text is None:
            text = self.text
        self._btn['text'] = text
        self._btn['state'] = state
        self._btn['command'] = command


class NormalSlider:
    """
    My normal slider, again with an updater function to update the slider.
    """

    def __init__(self, parent, from_=0, to=np.inf, resolution=1, start=0,
                 row=None, column=None, rowspan=1, columnspan=1, sticky=None, padx=0, pady=0):
        self._scale = tk.Scale(parent, from_=from_, to=to, orient='horizontal',
                               resolution=resolution, bg='white', borderwidth=0, highlightthickness=0)
        self._scale.set(start)
        self.parent = parent
        self.from_ = from_
        self.to = to
        self.resolution = resolution
        self.start = start
        self.row = row
        self.column = column
        self.rowspan = rowspan
        self.columnspan = columnspan
        self.sticky = sticky
        self.padx = padx
        self.pady = pady
        self._scale.grid(row=self.row, column=self.column, rowspan=self.rowspan, columnspan=self.columnspan,
                         sticky=sticky, padx=padx, pady=pady)

    def updater(self, from_=None, to=None, start=None):
        if from_ is None:
            from_ = self.from_
        if to is None:
            to = self.to
        if start is None:
            start = self.start
        self._scale.configure(from_=from_, to=to)
        self._scale.set(start)

        self.from_ = from_
        self.to = to
        self.start = start

    def get(self):
        return self._scale.get()


class NormalLabel:
    """
    My normal label, again with an updater function to update the label.
    """

    def __init__(self, parent, text=None, font=None, bd=None, relief=None,
                 row=None, column=None, rowspan=1, columnspan=1, sticky=None, padx=0, pady=0):
        self._label = tk.Label(parent, text=text, font=font, bd=bd, relief=relief, bg='white')
        self._label.grid(row=row, column=column, rowspan=rowspan, columnspan=columnspan,
                         sticky=sticky, padx=padx, pady=pady)
        self.parent = parent
        self.text = text
        self.font = font
        self.bd = bd
        self.relief = relief
        self.row = row
        self.column = column
        self.rowspan = rowspan
        self.columnspan = columnspan
        self.sticky = sticky
        self.padx = padx
        self.pady = pady

    def updater(self, text=None):
        if text is None:
            text = self.text
        self._label['text'] = text

# %% Progress Updater


class ProgressUpdaterGUI(ProgressUpdater):
    def __init__(self, gui, progress_task_status, progress_overall_status, current_task_status, time_done_status):
        super().__init__()
        self.gui = gui
        self.progress_task_status = progress_task_status
        self.progress_overall_status = progress_overall_status
        self.current_task_status = current_task_status
        self.time_done_status = time_done_status
        self.start_time = time.time()

    def update(self, new_dataset, message_bool):
        if new_dataset:
            self.progress_task_status.updater(text="0%")
            self.progress_overall_status.updater(text="{}%".format(int((self.current_dataset - 1)/self.total_datasets)))

            self.current_task_status.updater(text="Task #{}: {}".format(self.current_dataset, self.current_type))
        elif message_bool:
            self.current_task_status.updater(text=self.message_string)
        else:
            progress_percent = self.progress / self.total
            progress_percent_overall = progress_percent + (self.current_dataset - 1) * 100 / self.total_datasets
            self.progress_task_status.updater(text="{}%".format(int(progress_percent*100)))
            self.progress_overall_status.updater(text="{}%".format(int(progress_percent_overall*100)))

            time_taken = time.time() - self.start_time
            time_done_estimate = time_taken * 1 / progress_percent + self.start_time
            tr = time.localtime(time_done_estimate)
            time_text = "{:02d}:{:02d}:{:02d} {:02d}/{:02d}".format(tr[3], tr[4], tr[5], tr[2], tr[1])
            self.time_done_status.updater(text=time_text)

        self.gui.update()

# %% Footer


class FooterBase(tk.Frame):
    def __init__(self, controller):
        tk.Frame.__init__(self, controller)
        self.configure(bg='white')
        self.controller = controller

        label_version = tk.Label(self, text="MBx Python, version: " + __version__, font=FONT_LABEL, bg='white',
                                 anchor='w')
        label_version.grid(row=0, column=0, columnspan=20, sticky='EW', padx=PAD_SMALL)

        button_quit = ttk.Button(self, text="Quit", command=lambda: quit_gui(self.controller))
        button_quit.grid(row=0, column=44, columnspan=4, sticky='EW', padx=PAD_SMALL)

        for i in range(48):
            self.grid_columnconfigure(i, weight=1)


class Footer(FooterBase):
    def __init__(self, controller):
        super().__init__(controller)

        button_cancel = ttk.Button(self, text="Cancel", command=lambda: self.cancel())
        button_cancel.grid(row=0, column=40, columnspan=4, sticky='EW', padx=PAD_SMALL)

        for i in range(48):
            self.grid_columnconfigure(i, weight=1)

    def cancel(self):
        self.controller.show_page(MainPage)

# %% Controller


class MbxPython(tk.Tk):
    """
    Controller of GUI. This container calls the page we need
    """

    def __init__(self, proceed_question=None, *args, **kwargs):
        tk.Tk.__init__(self, *args, **kwargs)
        self.withdraw()

        tk.Tk.wm_title(self, "MBx Python")
        container = tk.Frame(self)

        container.pack(side="top", fill="both", expand=True)

        self.footer = FooterBase(self)
        self.footer.pack(side="bottom", fill="both")

        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.proceed_question = proceed_question
        self.progress_updater = None
        self.experiments = []
        self.experiment_to_link_name = None

        self.pages = {}
        page_tuple = (MainPage, LoadPage, ROIPage, TTPage, HSMPage)
        for to_load_page in page_tuple:
            page = to_load_page(container, self)
            self.pages[to_load_page] = page
            page.grid(row=0, column=0, sticky="nsew")
        self.show_page(MainPage)

        self.additional_settings()
        self.deiconify()

    @staticmethod
    def show_rois(frame, figure=None, roi_locations=None, roi_size=None, roi_offset=None):
        if figure is None:
            figure = plt.subplots(1)
        figure.updater(frame, roi_locations=roi_locations, roi_size=roi_size, roi_offset=roi_offset)

    def additional_settings(self):
        self.geometry(str(GUI_WIDTH) + "x" + str(GUI_HEIGHT) + "+" + str(GUI_WIDTH_START) + "+" + str(GUI_HEIGHT_START))
        self.iconbitmap(getcwd() + "\ico.ico")
        self.protocol("WM_DELETE_WINDOW", lambda: quit_gui(gui))

        ttk_style = ttk.Style(self)
        ttk_style.configure("Big.TButton", font=FONT_BUTTON_BIG)
        ttk_style.configure("Placeholder.TEntry", foreground="Grey")
        ttk_style.configure("TButton", font=FONT_BUTTON, background="Grey")
        ttk_style.configure("TSeparator", background="black")
        ttk_style.configure("TMenubutton", font=FONT_DROP, background="White")

    def show_page(self, page, experiment=None):
        if page == MainPage:
            self.footer.pack_forget()
            self.footer = FooterBase(self)
            self.footer.pack(side="bottom", fill="both")
        else:
            self.footer.pack_forget()
            self.footer = Footer(self)
            self.footer.pack(side="bottom", fill="both")
        page = self.pages[page]
        page.update_page(experiment=experiment)
        page.tkraise()

# %% Base page


class BasePage(tk.Frame):
    def __init__(self, container, controller):
        tk.Frame.__init__(self, container)
        self.configure(bg='white')
        self.controller = controller

        self.column_row_configure()

    def column_row_configure(self):
        for i in range(48):
            self.grid_columnconfigure(i, weight=1, minsize=18)
        for i in range(20):
            self.grid_rowconfigure(i, weight=1)

    def update_page(self, experiment=None):
        pass

# %% Main page


class MainPage(BasePage):
    def __init__(self, container, controller):
        super().__init__(container, controller)

        label_new = tk.Label(self, text="New", font=FONT_HEADER, bg='white')
        label_new.grid(row=0, column=0, columnspan=16, rowspan=1, sticky='EW', padx=PAD_SMALL)

        button_new_experiment = BigButton(self, text="ADD EXPERIMENT", height=int(GUI_HEIGHT / 4),
                                          width=int(GUI_WIDTH / 6), command=lambda: self.add_experiment())
        button_new_experiment.grid(row=1, column=0, columnspan=16, rowspan=4, sticky='EW', padx=PAD_SMALL)

        button_new_dataset = BigButton(self, text="ADD DATASET", height=int(GUI_HEIGHT / 4),
                                       width=int(GUI_WIDTH / 6), command=lambda: self.add_dataset())
        button_new_dataset.grid(row=5, column=0, columnspan=16, rowspan=4, sticky='EW', padx=PAD_SMALL)

        label_loaded = tk.Label(self, text="Loaded", font=FONT_HEADER, bg='white')
        label_loaded.grid(row=0, column=16, columnspan=16, sticky='EW', padx=PAD_SMALL)

        self.listbox_loaded = tk.Listbox(self)
        self.listbox_loaded.grid(row=1, column=16, columnspan=16, rowspan=8, sticky='NSEW', padx=PAD_SMALL)
        self.listbox_loaded.configure(justify="center")

        button_loaded_delete = ttk.Button(self, text="Delete", command=lambda: self.delete_experiment())
        button_loaded_delete.grid(row=9, column=16, columnspan=8, sticky='EW', padx=PAD_SMALL)

        button_loaded_deselect = ttk.Button(self, text="Deselect", command=lambda: self.deselect_experiment())
        button_loaded_deselect.grid(row=9, column=24, columnspan=8, sticky='EW', padx=PAD_SMALL)

        label_queued = tk.Label(self, text="Queued", font=FONT_HEADER, bg='white')
        label_queued.grid(row=0, column=32, columnspan=16, sticky='EW', padx=PAD_SMALL)

        self.listbox_queued = tk.Listbox(self)
        self.listbox_queued.grid(row=1, column=32, columnspan=16, rowspan=8, sticky='NSEW', padx=PAD_SMALL)
        self.listbox_queued.configure(justify="center")
        self.listbox_queued.bindtags((self.listbox_queued, self, "all"))

        button_run = ttk.Button(self, text="Run", command=lambda: self.run())
        button_run.grid(row=9, column=40, columnspan=8, sticky='EW', padx=PAD_SMALL)

        label_progress_task = tk.Label(self, text="Task Progress", font=FONT_HEADER, bg='white')
        label_progress_task.grid(row=13, column=0, columnspan=8, rowspan=2, sticky='EW', padx=PAD_SMALL)

        label_progress_overall = tk.Label(self, text="Overall Progress", font=FONT_HEADER, bg='white')
        label_progress_overall.grid(row=15, column=0, columnspan=8, sticky='EW', padx=PAD_SMALL)

        self.label_progress_task_status = NormalLabel(self, text="Not yet started", bd=1, relief='sunken',
                                                      row=13, column=8, columnspan=16, rowspan=2,
                                                      sticky="ew", font=FONT_LABEL)
        self.label_progress_overall_status = NormalLabel(self, text="Not yet started", bd=1, relief='sunken',
                                                         row=15, column=8, columnspan=16, rowspan=2,
                                                         sticky="ew", font=FONT_LABEL)

        label_current_task = tk.Label(self, text="Current Task", font=FONT_HEADER, bg='white')
        label_current_task.grid(row=13, column=32, columnspan=8, rowspan=2, sticky='EW', padx=PAD_SMALL)

        self.label_current_task_status = NormalLabel(self, text="Not yet started", bd=1, relief='sunken',
                                                     row=13, column=40, columnspan=8, rowspan=2,
                                                     sticky="ew", font=FONT_LABEL)

        label_time_done = tk.Label(self, text="Time Done", font=FONT_HEADER, bg='white')
        label_time_done.grid(row=15, column=32, columnspan=8, rowspan=2, sticky='EW', padx=PAD_SMALL)

        self.label_time_done_status = NormalLabel(self, text="Not yet started", bd=1, relief='sunken',
                                                  row=15, column=40, columnspan=8, rowspan=2,
                                                  sticky="ew", font=FONT_LABEL)

        self.controller.progress_updater = ProgressUpdaterGUI(self, self.label_progress_task_status,
                                                              self.label_progress_overall_status,
                                                              self.label_current_task_status,
                                                              self.label_time_done_status)

    def add_experiment(self):
        self.controller.show_page(LoadPage)
        self.controller.experiment_to_link_name = None

    def add_dataset(self):
        try:
            selected = self.listbox_loaded.get(self.listbox_loaded.curselection())
            name = selected.split(" ")[-1]
            self.controller.experiment_to_link_name = name
            self.controller.show_page(LoadPage)
        except:
            tk.messagebox.showerror("ERROR", "No experiment selected, please select one to link dataset to")

    def delete_experiment(self):
        try:
            selected = self.listbox_loaded.get(self.listbox_loaded.curselection())
            name = selected.split(" ")[-1]
            for index, experiment in enumerate(self.controller.experiments):
                if name in experiment.name:
                    del self.controller.experiments[index]
                    break
            self.update_page()
        except:
            return

    def deselect_experiment(self):
        self.listbox_loaded.selection_clear(0, "end")

    def run(self):
        pass  # TO DO

    def update_page(self, experiment=None):
        self.listbox_loaded.delete(0, 'end')
        self.listbox_queued.delete(0, 'end')

        for index, experiment in enumerate(self.controller.experiments, 1):
            self.listbox_loaded.insert('end', "Experiment {}: {}".format(index, experiment.name))
            for dataset in experiment.datasets:
                self.listbox_queued.insert('end', "Experiment {}: {} ({})".format(index, dataset.name, dataset.type))

# %% Loading page


class LoadPage(BasePage):
    """
    Loading page. On this page, there are only two big buttons to select which type of dataset you want to load
    """
    def __init__(self, container, controller):
        super().__init__(container, controller)

        button1 = BigButton(self, text="TT", height=int(GUI_HEIGHT / 6),
                            width=int(GUI_WIDTH / 8),
                            command=lambda: self.load_nd2("TT"))
        button1.grid(row=0, column=24, columnspan=1, rowspan=20, padx=PAD_SMALL)

        button2 = BigButton(self, text="HSM", height=int(GUI_HEIGHT / 6),
                            width=int(GUI_WIDTH / 8),
                            command=lambda: self.load_nd2("HSM"))
        button2.grid(row=0, column=25, columnspan=1, rowspan=20, padx=PAD_SMALL)

    def load_nd2(self, dataset_type):
        filename = askopenfilename(filetypes=FILETYPES,
                                   title="Select nd2",
                                   initialdir=getcwd())

        if len(filename) == 0:
            return

        if self.controller.experiment_to_link_name is None:
            experiment = Experiment(dataset_type, filename, self.controller.proceed_question,
                                    self.controller.progress_updater, self.controller.show_rois)
            self.controller.experiments.append(experiment)
            self.controller.show_page(ROIPage, experiment=experiment)
        else:
            experiment_to_link = [experiment for experiment in self.controller.experiments if
                                  self.controller.experiment_to_link_name in experiment.name][0]
            if dataset_type == "TT":
                experiment_to_link.init_new_tt(filename)
                self.controller.show_page(TTPage, experiment=experiment_to_link)
            else:
                experiment_to_link.init_new_hsm(filename)
                self.controller.show_page(HSMPage, experiment=experiment_to_link)

# %% ROIPage


class ROIPage(BasePage):
    def __init__(self, container, controller):
        super().__init__(container, controller)

        self.experiment = None
        self.default_settings = None
        self.saved_settings = None
        self.histogram_fig = None
        self.to_hist = None

        label_name = tk.Label(self, text="Name", font=FONT_LABEL, bg='white')
        label_name.grid(row=0, column=0, columnspan=8, sticky='EW', padx=PAD_BIG)

        self.entry_name = EntryPlaceholder(self, "TBD", width=INPUT_BIG)
        self.entry_name.grid(row=0, column=8, columnspan=24, sticky='EW')

        label_min_int = tk.Label(self, text="Minimum Intensity", font=FONT_LABEL, bg='white')
        label_min_int.grid(row=2, column=0, columnspan=8, sticky='EW', padx=PAD_SMALL)
        self.slider_min_int = NormalSlider(self, from_=0, to=1000,
                                           row=3, column=0, columnspan=8, sticky='EW', padx=PAD_SMALL)

        button_min_int_histogram = ttk.Button(self, text="Graph",
                                              command=lambda: self.fun_histogram("min_int"))
        button_min_int_histogram.grid(row=3, column=16, columnspan=8, sticky='EW', padx=PAD_SMALL)
        button_min_int_histogram_select = ttk.Button(self, text="Select min",
                                                     command=lambda: self.histogram_select("min_int"))
        button_min_int_histogram_select.grid(row=3, column=8, columnspan=8, sticky='EW', padx=PAD_SMALL)
        button_max_int_histogram_select = ttk.Button(self, text="Select max",
                                                     command=lambda: self.histogram_select("max_int"))
        button_max_int_histogram_select.grid(row=3, column=24, columnspan=8, sticky='EW', padx=PAD_SMALL)

        label_max_int = tk.Label(self, text="Maximum Intensity", font=FONT_LABEL, bg='white')
        label_max_int.grid(row=2, column=32, columnspan=8, sticky='EW', padx=PAD_SMALL)
        self.slider_max_int = NormalSlider(self, from_=0, to=5000,
                                           row=3, column=32, columnspan=8, sticky='EW', padx=PAD_SMALL)

        label_min_sigma = tk.Label(self, text="Minimum Sigma", font=FONT_LABEL, bg='white')
        label_min_sigma.grid(row=4, column=0, columnspan=8, sticky='EW', padx=PAD_SMALL)
        self.slider_min_sigma = NormalSlider(self, from_=0, to=5, resolution=0.01,
                                             row=5, column=0, columnspan=8, sticky='EW', padx=PAD_SMALL)

        button_min_sigma_histogram = ttk.Button(self, text="Graph",
                                                command=lambda: self.fun_histogram("min_sigma"))
        button_min_sigma_histogram.grid(row=5, column=16, columnspan=8, sticky='EW', padx=PAD_SMALL)
        button_min_sigma_histogram_select = ttk.Button(self, text="Select min",
                                                       command=lambda: self.histogram_select("min_sigma"))
        button_min_sigma_histogram_select.grid(row=5, column=8, columnspan=8, sticky='EW', padx=PAD_SMALL)
        button_max_sigma_histogram_select = ttk.Button(self, text="Select max",
                                                       command=lambda: self.histogram_select("max_sigma"))
        button_max_sigma_histogram_select.grid(row=5, column=24, columnspan=8, sticky='EW', padx=PAD_SMALL)

        label_max_sigma = tk.Label(self, text="Maximum Sigma", font=FONT_LABEL, bg='white')
        label_max_sigma.grid(row=4, column=32, columnspan=8, sticky='EW', padx=PAD_SMALL)
        self.slider_max_sigma = NormalSlider(self, from_=0, to=10, resolution=0.01,
                                             row=5, column=32, columnspan=8, sticky='EW', padx=PAD_SMALL)

        line = ttk.Separator(self, orient='horizontal')
        line.grid(row=7, column=0, rowspan=1, columnspan=40, sticky='we')

        label_advanced_settings = tk.Label(self, text="Advanced settings", font=FONT_SUBHEADER, bg='white')
        label_advanced_settings.grid(row=9, column=0, columnspan=40, sticky='EW', padx=PAD_SMALL)

        label_min_corr = tk.Label(self, text="Minimum Correlation", font=FONT_LABEL, bg='white')
        label_min_corr.grid(row=9, column=0, columnspan=8, sticky='EW', padx=PAD_SMALL)
        self.slider_min_corr = NormalSlider(self, from_=0, to=1, resolution=0.005,
                                            row=10, column=0, columnspan=8, sticky='EW', padx=PAD_SMALL)

        button_min_corr_histogram = ttk.Button(self, text="Graph",
                                               command=lambda: self.fun_histogram("corr_min"))
        button_min_corr_histogram.grid(row=10, column=16, columnspan=8, sticky='EW', padx=PAD_SMALL)
        button_min_corr_histogram_select = ttk.Button(self, text="Graph select",
                                                      command=lambda: self.histogram_select("corr_min"))
        button_min_corr_histogram_select.grid(row=10, column=8, columnspan=8, sticky='EW', padx=PAD_SMALL)

        label_all_figures = tk.Label(self, text="All Figures", font=FONT_LABEL, bg='white')
        label_all_figures.grid(row=12, column=0, columnspan=5, sticky='EW', padx=PAD_SMALL)
        self.variable_all_figures = tk.StringVar(self, value=False)
        check_figures = tk.Checkbutton(self, variable=self.variable_all_figures, onvalue=True, offvalue=False,
                                       bg="white")
        check_figures.grid(row=12, column=5, columnspan=5, sticky='EW', padx=PAD_SMALL)

        label_filter_size = tk.Label(self, text="Filter size", bg='white', font=FONT_LABEL)
        label_filter_size.grid(row=12, column=10, columnspan=5, sticky='EW', padx=PAD_SMALL)
        self.entry_filter_size = EntryPlaceholder(self, "9", width=INPUT_SMALL)
        self.entry_filter_size.grid(row=12, column=15, columnspan=5)

        label_roi_side = tk.Label(self, text="Side spacing", bg='white', font=FONT_LABEL)
        label_roi_side.grid(row=12, column=20, columnspan=5, sticky='EW', padx=PAD_SMALL)
        self.entry_roi_side = EntryPlaceholder(self, "11", width=INPUT_SMALL)
        self.entry_roi_side.grid(row=12, column=25, columnspan=5)

        label_inter_roi = tk.Label(self, text="ROI spacing", bg='white', font=FONT_LABEL)
        label_inter_roi.grid(row=12, column=30, columnspan=5, sticky='EW', padx=PAD_SMALL)
        self.entry_inter_roi = EntryPlaceholder(self, "6", width=INPUT_SMALL)
        self.entry_inter_roi.grid(row=12, column=35, columnspan=5)

        line = ttk.Separator(self, orient='horizontal')
        line.grid(row=14, column=0, rowspan=1, columnspan=40, sticky='we')

        button_find_rois = ttk.Button(self, text="Find ROIs", command=lambda: self.fit_rois())
        button_find_rois.grid(row=17, column=0, columnspan=8, sticky='EW', padx=PAD_SMALL)

        self.label_number_of_rois = NormalLabel(self, text="TBD", row=17, column=8, columnspan=8, font=FONT_LABEL,
                                                padx=PAD_SMALL, sticky='EW')

        button_restore = ttk.Button(self, text="Restore default",
                                    command=lambda: self.restore_default())
        button_restore.grid(row=17, column=16, columnspan=8, sticky='EW', padx=PAD_SMALL)
        self.button_restore_saved = NormalButton(self, text="Restore saved",
                                                 state='disabled',
                                                 command=lambda: self.restore_saved(),
                                                 row=17, column=24,
                                                 columnspan=8, sticky='EW', padx=PAD_SMALL)

        button_save = ttk.Button(self, text="Save", command=lambda: self.save_roi_settings())
        button_save.grid(row=17, column=32, columnspan=8, sticky='EW', padx=PAD_SMALL)

        self.figure = FigureFrame(self, height=GUI_WIDTH * 0.4, width=GUI_WIDTH * 0.4, dpi=DPI)
        self.figure.grid(row=0, column=40, columnspan=8, rowspan=18, sticky='EW', padx=PAD_SMALL)

        button_accept = ttk.Button(self, text="Accept & Continue", command=lambda: self.accept())
        button_accept.grid(row=18, column=44, columnspan=4, rowspan=2, sticky='EW', padx=PAD_SMALL)

    def fun_histogram(self, variable):
        """
        Actually makes the histogram
        Parameters
        ----------
        variable : Variable to make histogram of
        Returns
        -------
        None, outputs figure
        """
        if variable == "min_int" or variable == "max_int":
            self.to_hist = self.experiment.roi_finder.main(return_int=True)
        elif variable == "peak_min":
            self.to_hist = np.ravel(self.experiment.frame_for_rois)
        elif variable == "corr_min":
            self.to_hist = self.experiment.roi_finder.main(return_corr=True)
        else:
            self.to_hist = self.experiment.roi_finder.main(return_sigmas=True)

        self.histogram_fig = plt.figure(figsize=(6.4 * 1.2, 4.8 * 1.2))

        self.make_histogram(variable)

    def make_histogram(self, variable):
        """
        Makes histograms of parameters.
        Parameters
        ----------
        variable : The parameter to make a histogram of
        Returns
        -------
        None, output figure
        """
        fig_sub = self.histogram_fig.add_subplot(111)
        hist, bins, _ = fig_sub.hist(self.to_hist, bins='auto')

        min_int = self.slider_min_int.get()
        max_int = self.slider_max_int.get()
        min_sigma = self.slider_min_sigma.get()
        max_sigma = self.slider_max_sigma.get()
        min_corr = self.slider_min_corr.get()

        if variable == "min_int" or variable == "max_int":
            self.histogram_fig.clear()
            logbins = np.logspace(np.log10(bins[0]), np.log10(bins[-1]), len(bins))
            plt.hist(self.to_hist, bins=logbins)
            plt.title("Intensity. Use graph select to change threshold")
            plt.axvline(x=min_int, color='red', linestyle='--')
            plt.axvline(x=max_int, color='red', linestyle='--')
            plt.xscale('log')
        elif variable == "min_sigma" or variable == "max_sigma":
            plt.title("Sigma. Use graph select to change threshold")
            plt.axvline(x=min_sigma, color='red', linestyle='--')
            plt.axvline(x=max_sigma, color='red', linestyle='--')
        else:
            self.histogram_fig.clear()
            logbins = np.logspace(np.log10(bins[0]), np.log10(bins[-1]), len(bins))
            plt.hist(self.to_hist, bins=logbins)
            plt.title("Correlation values for ROIs. Use graph select to change threshold")
            plt.axvline(x=min_corr, color='red', linestyle='--')
            plt.xscale('log')

        self.histogram_fig.show()

    def histogram_select(self, variable):
        """
        Allows user to select from histogram to change slider
        Parameters
        ----------
        variable : variable to change
        Returns
        -------
        None.
        """
        try:
            click = self.histogram_fig.ginput(1)
        except AttributeError:
            tk.messagebox.showerror("You cannot do that", "You cannot click on a figure without having a figure open")
            return

        if variable == "min_int":
            self.slider_min_int.updater(start=int(click[0][0]))
        elif variable == 'max_int':
            self.slider_max_int.updater(start=int(click[0][0]))
        elif variable == "min_sigma":
            self.slider_min_sigma.updater(start=click[0][0])
        elif variable == "max_sigma":
            self.slider_max_sigma.updater(start=click[0][0])
        else:
            self.slider_min_corr.updater(start=click[0][0])

        self.histogram_fig.clear()
        self.make_histogram(variable)

    def read_out_settings(self):
        """
        Function that reads out all the settings, and saves it to a dict which it returns
        Returns
        -------
        settings: a dictionary of all read-out settings
        """
        int_min = self.slider_min_int.get()
        int_max = self.slider_max_int.get()
        sigma_min = self.slider_min_sigma.get()
        sigma_max = self.slider_max_sigma.get()
        corr_min = self.slider_min_corr.get()
        roi_size = 7  # hard-coded as 7 for ROI finding
        all_figures = bool(int(self.variable_all_figures.get()))

        try:
            filter_size = int(self.entry_filter_size.get())
            roi_side = int(self.entry_roi_side.get())
            inter_roi = int(self.entry_inter_roi.get())
        except:
            tk.messagebox.showerror("ERROR", "Filter size, side spacing, and ROI spacing must all be integers")
            return {}, False

        settings = {'int_max': int_max, 'int_min': int_min,
                    'sigma_min': sigma_min, 'sigma_max': sigma_max,
                    'corr_min': corr_min, 'roi_size': roi_size, 'filter_size': filter_size,
                    'roi_side': roi_side, 'inter_roi': inter_roi, 'all_figures': all_figures}

        return settings, True

    def fit_rois(self):
        settings, success = self.read_out_settings()
        if success is False:
            return False

        if settings['roi_side'] < int((settings['roi_size'] - 1) / 2):
            tk.messagebox.showerror("ERROR", "Distance to size cannot be smaller than 1D ROI size")
            return False
        if settings['filter_size'] % 2 != 1:
            tk.messagebox.showerror("ERROR", "Filter size should be odd")
            return False

        self.experiment.change_rois(settings)
        self.experiment.show_rois("Experiment", figure=self.figure)
        self.label_number_of_rois.updater(text="{} ROIs found".format(len(self.experiment.rois)))

        return True

    def restore_default(self):
        if self.default_settings is None:
            self.default_settings = self.experiment.roi_finder.get_settings()
        else:
            pass
        self.slider_min_int.updater(from_=0, to=self.default_settings['int_max'] / 4,
                                    start=self.default_settings['int_min'])
        self.slider_max_int.updater(from_=0, to=self.default_settings['int_max'],
                                    start=self.default_settings['int_max'])
        self.slider_min_sigma.updater(from_=0, to=self.default_settings['sigma_max'],
                                      start=self.default_settings['sigma_min'])
        self.slider_max_sigma.updater(from_=0, to=self.default_settings['sigma_max'],
                                      start=self.default_settings['sigma_max'])
        self.slider_min_corr.updater(from_=0, to=1, start=self.default_settings['corr_min'])

        self.variable_all_figures.set(False)

        self.entry_filter_size.updater()
        self.entry_roi_side.updater()
        self.entry_inter_roi.updater()

        self.update()
        self.fit_rois()

    def restore_saved(self):
        """
        Restores saved settings to sliders etc.
        Returns
        -------
        None, updates GUI
        """
        settings = self.saved_settings

        self.slider_min_int.updater(from_=0, to=self.default_settings['int_max'] / 4,
                                    start=settings['int_min'])
        self.slider_max_int.updater(from_=0, to=self.default_settings['int_max'],
                                    start=settings['int_max'])
        self.slider_min_sigma.updater(from_=0, to=self.default_settings['sigma_max'],
                                      start=settings['sigma_min'])
        self.slider_max_sigma.updater(from_=0, to=self.default_settings['sigma_max'],
                                      start=settings['sigma_max'])
        self.slider_min_corr.updater(from_=0, to=1, start=settings['corr_min'])

        self.entry_filter_size.updater(settings['filter_size'])
        self.entry_roi_side.updater(settings['roi_side'])
        self.entry_inter_roi.updater(settings['inter_roi'])

        self.variable_all_figures.set(settings['all_figures'])

        self.experiment.change_rois(settings)
        self.experiment.show_rois("Experiment", figure=self.figure)
        self.label_number_of_rois.updater(text="{} ROIs found".format(len(self.experiment.rois)))
        self.update()

    def save_roi_settings(self):
        success = self.fit_rois()
        if not success:
            return

        self.saved_settings, _ = self.read_out_settings()
        self.button_restore_saved.updater()

    def accept(self):
        if self.controller.proceed_question("Are you sure?", "You cannot change settings later.") is False:
            return
        settings, success = self.read_out_settings()
        if success is False:
            return
        self.experiment.change_rois(settings)

        name = self.entry_name.get()
        settings_experiment = {'All Figures': settings['all_figures']}
        self.experiment.finalize_rois(name, settings_experiment)

        if self.experiment.created_by == "TT":
            self.controller.show_page(TTPage, experiment=self.experiment)
        else:
            self.controller.show_page(HSMPage, experiment=self.experiment)
        self.experiment = None
        self.default_settings = None
        self.saved_settings = None
        self.histogram_fig = None
        self.to_hist = None

    def update_page(self, experiment=None):
        self.experiment = experiment

        self.entry_name.updater(placeholder=self.experiment.datasets[-1].name)  # take name for only dataset in exp
        self.figure.updater(self.experiment.frame_for_rois)

        self.restore_default()

# %% TTPage


class TTPage(BasePage):
    def __init__(self, container, controller):
        super().__init__(container, controller)

        self.experiment = None

        label_loaded_video = tk.Label(self, text="Loaded video", font=FONT_HEADER, bg='white')
        label_loaded_video.grid(row=0, column=0, columnspan=8, rowspan=1, sticky='EW', padx=PAD_SMALL)
        self.label_loaded_video_status = NormalLabel(self, text="XX", row=0, column=8, columnspan=16, rowspan=1,
                                                     sticky="ew", font=FONT_LABEL)

        label_name = tk.Label(self, text="Name", font=FONT_LABEL, bg='white')
        label_name.grid(row=1, column=0, columnspan=8, sticky='EW', padx=PAD_BIG)

        self.entry_name = EntryPlaceholder(self, "TBD", width=INPUT_BIG)
        self.entry_name.grid(row=1, column=8, columnspan=16, sticky='EW')

        label_x_min_max = tk.Label(self, text="x min and max", font=FONT_LABEL, bg='white')
        label_x_min_max.grid(row=3, column=0, columnspan=8, sticky='EW', padx=PAD_SMALL)
        self.entry_x_min = EntryPlaceholder(self, "Leave empty for start", width=INPUT_BIG)
        self.entry_x_min.grid(row=3, column=8, columnspan=8, padx=PAD_SMALL)
        self.entry_x_max = EntryPlaceholder(self, "Leave empty for end", width=INPUT_BIG)
        self.entry_x_max.grid(row=3, column=16, columnspan=8, padx=PAD_SMALL)

        label_y_min_max = tk.Label(self, text="y min and max", font=FONT_LABEL, bg='white')
        label_y_min_max.grid(row=4, column=0, columnspan=8, sticky='EW', padx=PAD_SMALL)
        self.entry_y_min = EntryPlaceholder(self, "Leave empty for start", width=INPUT_BIG)
        self.entry_y_min.grid(row=4, column=8, columnspan=8, padx=PAD_SMALL)
        self.entry_y_max = EntryPlaceholder(self, "Leave empty for end", width=INPUT_BIG)
        self.entry_y_max.grid(row=4, column=16, columnspan=8, padx=PAD_SMALL)

        button_find_rois = ttk.Button(self, text="Find ROIs", command=lambda: self.fit_rois())
        button_find_rois.grid(row=6, column=8, columnspan=8, sticky='EW', padx=PAD_SMALL)

        self.figure_dataset = FigureFrame(self, height=GUI_WIDTH * 0.35, width=GUI_WIDTH * 0.35, dpi=DPI)
        self.figure_dataset.grid(row=0, column=24, columnspan=12, rowspan=8, sticky='EW', padx=PAD_SMALL)

        self.figure_experiment = FigureFrame(self, height=GUI_WIDTH * 0.35, width=GUI_WIDTH * 0.35, dpi=DPI)
        self.figure_experiment.grid(row=0, column=36, columnspan=12, rowspan=8, sticky='EW', padx=PAD_SMALL)

        line = ttk.Separator(self, orient='horizontal')
        line.grid(row=8, column=0, rowspan=1, columnspan=48, sticky='we')

        label_method = tk.Label(self, text="Method", font=FONT_LABEL, bg='white')
        label_method.grid(row=12, column=0, columnspan=12, sticky='EW', padx=PAD_SMALL)
        self.variable_method = tk.StringVar(self)
        drop_method = ttk.OptionMenu(self, self.variable_method, fit_options[1], *fit_options)
        drop_method.grid(row=13, column=0, columnspan=12, sticky="ew")

        label_rejection = tk.Label(self, text="Rejection", bg='white', font=FONT_LABEL)
        label_rejection.grid(row=12, column=12, columnspan=12, sticky='EW', padx=PAD_SMALL)
        self.variable_rejection = tk.StringVar(self)
        drop_rejection = ttk.OptionMenu(self, self.variable_rejection, rejection_options[0], *rejection_options)
        drop_rejection.grid(row=13, column=12, columnspan=12, sticky='EW', padx=PAD_SMALL)

        label_cores = tk.Label(self, text="#cores", font=FONT_LABEL, bg='white')
        label_cores.grid(row=12, column=24, columnspan=6, sticky='EW', padx=PAD_BIG)
        total_cores = mp.cpu_count()
        cores_options = [1, int(total_cores / 2), int(total_cores * 3 / 4), int(total_cores)]
        self.variable_cores = tk.IntVar(self)
        drop_cores = ttk.OptionMenu(self, self.variable_cores, cores_options[0], *cores_options)
        drop_cores.grid(row=13, column=24, columnspan=6, sticky='EW', padx=PAD_BIG)

        label_dimensions = tk.Label(self, text="pixels or nm", font=FONT_LABEL, bg='white')
        label_dimensions.grid(row=12, column=30, columnspan=6, sticky='EW', padx=PAD_BIG)
        dimension_options = ["nm", "pixels"]
        self.variable_dimensions = tk.StringVar(self)
        drop_dimension = ttk.OptionMenu(self, self.variable_dimensions, dimension_options[0], *dimension_options)
        drop_dimension.grid(row=13, column=30, columnspan=6, sticky='EW', padx=PAD_BIG)

        label_used_roi_spacing = tk.Label(self, text="Used ROI spacing", bg='white', font=FONT_LABEL)
        label_used_roi_spacing.grid(row=16, column=0, rowspan=2, columnspan=8, sticky='EW', padx=PAD_SMALL)
        self.label_roi_spacing_status = NormalLabel(self, text="TBD", row=16, column=8, rowspan=2, columnspan=4,
                                                    sticky='EW', padx=PAD_SMALL, font=FONT_LABEL)

        label_roi_size = tk.Label(self, text="ROI size", bg='white', font=FONT_LABEL)
        label_roi_size.grid(row=18, column=0, columnspan=6, rowspan=2, sticky='EW', padx=PAD_SMALL)
        self.variable_roi_size = tk.StringVar(self)
        drop_roi_size = ttk.OptionMenu(self, self.variable_roi_size, roi_size_options[0], *roi_size_options)
        drop_roi_size.grid(row=18, column=6, columnspan=6, rowspan=2, sticky='EW', padx=PAD_SMALL)

        label_begin_frame = tk.Label(self, text="Begin frame", font=FONT_LABEL, bg='white')
        label_begin_frame.grid(row=16, column=12, rowspan=2, columnspan=12, sticky='EW', padx=PAD_BIG)
        self.entry_begin_frame = EntryPlaceholder(self, "Leave empty for start", width=INPUT_BIG)
        self.entry_begin_frame.grid(row=18, column=12, rowspan=2, columnspan=12)

        label_end_frame = tk.Label(self, text="End frame", font=FONT_LABEL, bg='white')
        label_end_frame.grid(row=16, column=24, rowspan=2, columnspan=6, sticky='EW', padx=PAD_BIG)
        self.entry_end_frame = EntryPlaceholder(self, "Leave empty for end", width=INPUT_BIG)
        self.entry_end_frame.grid(row=18, column=24, rowspan=2, columnspan=6)

        self.button_add_to_queue = NormalButton(self, text="Add to queue", state='disabled',
                                                row=18, column=42, columnspan=6, rowspan=2, sticky='EW', padx=PAD_SMALL)

    @staticmethod
    def check_invalid_input(input_string, start):
        def is_int(to_check):
            try:
                int(to_check)
                return True
            except:
                return False

        if start:
            if input_string == "Leave empty for start" or is_int(input_string):
                return False
        else:
            if input_string == "Leave empty for end" or is_int(input_string):
                return False
        return True

    def fit_rois(self):
        x_min = self.entry_x_min.get()
        x_max = self.entry_x_max.get()
        y_min = self.entry_y_min.get()
        y_max = self.entry_y_max.get()
        if self.check_invalid_input(x_min, True) or self.check_invalid_input(y_max, False) or\
           self.check_invalid_input(y_min, True) or self.check_invalid_input(y_max, False):
            tk.messagebox.showerror("ERROR", "x min and max and y min and max must all be integers")
            return

        settings_correlation = {'x_min': x_min, 'x_max': x_max,
                                'y_min': y_min, 'y_max': y_max}

        self.experiment.find_rois_dataset(settings_correlation)
        self.experiment.show_rois("Dataset", self.figure_dataset)
        self.button_add_to_queue.updater(command=lambda: self.add_to_queue())

    def add_to_queue(self):
        name = self.entry_name.get()
        method = self.variable_method.get()
        rejection_type = self.variable_rejection.get()
        n_processes = self.variable_cores.get()
        dimension = self.variable_dimensions.get()
        frame_begin = self.entry_begin_frame.get()
        frame_end = self.entry_end_frame.get()
        roi_size = int(self.variable_roi_size.get()[0])

        if self.check_invalid_input(frame_begin, True) or self.check_invalid_input(frame_end, False):
            tk.messagebox.showerror("ERROR", "Frame begin and frame end must be integers")
            return

        settings_runtime = {'method': method, 'rejection': rejection_type, '#cores': n_processes,
                            'roi_size': roi_size, "pixels_or_nm": dimension, 'name': name,
                            'frame_begin': frame_begin, 'frame_end': frame_end}

        status = self.experiment.add_to_queue(settings_runtime)
        if status is False:
            tk.messagebox.askokcancel("Check again", "Settings are not allowed. Check again.")

        self.controller.show_page(MainPage)

    def update_page(self, experiment=None):
        self.experiment = experiment
        experiment.show_rois("Experiment", self.figure_experiment)
        experiment.show_rois("Dataset", self.figure_dataset)

        self.label_loaded_video_status.updater(text=self.experiment.datasets[-1].name)
        self.entry_name.updater(placeholder=self.experiment.datasets[-1].name)
        self.label_roi_spacing_status.updater(text=self.experiment.roi_finder.get_settings()['inter_roi'])

# %% HSMPage


class HSMPage(BasePage):
    def __init__(self, container, controller):
        super().__init__(container, controller)

# %% START GUI and declare styles (how things look)


if __name__ == '__main__':
    mp.freeze_support()
    divertor = DivertorErrorsGUI()
    warnings.showwarning = divertor.warning
    gui = MbxPython(proceed_question=proceed_question)

    #  tk.Tk.report_callback_exception = divertor.error
    plt.ioff()
    gui.mainloop()
