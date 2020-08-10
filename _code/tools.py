# -*- coding: utf-8 -*-
"""
Created on Sun May 31 23:27:01 2020

@author: Dion Engels
MBx Python Data Analysis

Tools

Some additional tools used by MBx Python

----------------------------

v0.1: Save to CSV & Mat: 31/05/2020
v0.2: also switch array: 04/06/2020
v0.3: cleaned up: 24/07/2020
v0.4: settings and results text output: 25/07/2020
v0.5: own ND2Reader class to prevent warnings: 29/07/2020
v0.6: save drift and save figures: 03/08/2020
v0.6.1: better MATLAB ROI and Drift output
v0.7: metadata v2
v0.8: metadata v3
v1.0: bug fixes
v1.0.1: metadata goldmine found, to be implemented
v1.1: emptied out: 09/08/2020

"""
from numpy import zeros


def change_to_pixels(results, metadata, method):
    pixelsize_nm = metadata['pixel_microns'] * 1000
    results[:, 2] *= pixelsize_nm  # y position to nm
    results[:, 3] *= pixelsize_nm  # x position to nm
    if "Gaussian" in method:
        results[:, 5] *= pixelsize_nm  # sigma y to nm
        results[:, 6] *= pixelsize_nm  # sigma x to nm

    return results


def roi_to_matlab_coordinates(roi_locs, height):

    roi_locs = switch_axis(roi_locs)
    roi_locs[:, 1] = height - roi_locs[:, 1]

    return roi_locs


def switch_results_to_matlab_coordinates(results, height, method, nm_or_pixels, metadata):

    results[:, 0] += 1  # add one to frame counting
    results[:, 1] += 1  # add one to ROI counting

    results[:, 2:4] = switch_axis_to_matlab_coordinates(results[:, 2:4], height, nm_or_pixels, metadata)  # switch x-y

    if "Gaussian" in method:
        results[:, 5:7] = switch_axis(results[:, 5:7])  # switch sigma x-y if Gaussian

    return results


def switch_axis_to_matlab_coordinates(array, height, nm_or_pixels="pixels", metadata=None):

    array = switch_axis(array)
    if nm_or_pixels == "nm":
        pixelsize_nm = metadata['pixel_microns'] * 1000
        array[:, 1] = height*pixelsize_nm - array[:, 1]
    else:
        array[:, 1] = height - array[:, 1]

    return array


def switch_axis(array):
    """
    Switches a single arrays values

    Parameters
    ----------
    array : array to switch

    Returns
    -------
    new : switched array

    """
    new = zeros(array.shape)
    new[:, 1] = array[:, 0]
    new[:, 0] = array[:, 1]
    return new
