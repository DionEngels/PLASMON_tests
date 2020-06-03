# -*- coding: utf-8 -*-
"""
Created on Sun May 31 22:58:08 2020

@author: Dion Engels
MBx Python Data Analysis

Gaussian fitting

----------------------------

v0.1: Setup: 31/05/2020
v0.2: Bugged rainSTORM inspired: 03/06/2020

"""
#%% Imports
import math
import numpy as np
from scipy import signal

#%% Code

def doastorm_3D():
    pass

#https://github.com/ZhuangLab/storm-analysis/tree/master/storm_analysis/daostorm_3d
    
class rainSTORM_Dion():
    
    def __init__(self, metadata, ROI_size, wavelength):
        self.result = []
        self.ROI_size = ROI_size
        self.ROI_size_1D = int((self.ROI_size-1)/2)
        self.allowSig = [0.25, self.ROI_size_1D+1]
        self.maxIts = 60
        self.maxtol = 0.2
        self.mintol = 0.2
        self.allowX = 1
        self.initSig = wavelength/(2*metadata['NA']*math.sqrt(8*math.log(2)))/(metadata['calibration_um']*1000)
        
        
    def determine_threshold(self, frame, ROI_locations, threshold):
        boolean = np.ones(frame.shape,dtype=int)
        
        for x,y in ROI_locations:
            if x < self.ROI_size_1D:
                x_min = 0
            else:
                x_min = int(x-self.ROI_size_1D)
            if x > frame.shape[0]-self.ROI_size_1D:
                x_max = frame.shape[0]
            else:
                x_max = int(x+self.ROI_size_1D)
            if y < self.ROI_size_1D:
                y_min = 0
            else:
                y_min = int(y-self.ROI_size_1D)
            if y > frame.shape[1]-self.ROI_size_1D:
                y_max = frame.shape[0]
            else:
                y_max = int(y+self.ROI_size_1D)
            boolean[x_min:x_max,y_min:y_max]  =np.zeros([x_max-x_min,y_max-y_min])
        self.ROI_zones = np.array(np.ones(boolean.shape)-boolean,dtype=bool)
        self.bg_mean = np.mean(frame[boolean==1])
        self.threshold = self.bg_mean + threshold*math.sqrt(self.bg_mean)
            
    
    def main(self, ROI_locations, frames, metadata):
        for frame_index, frame in enumerate(frames):
            frame_result = self.main_loop(frame, frame_index)
            if frame_index == 0:
                self.result = frame_result
            else:
                self.result = np.vstack((self.result,frame_result))
                
            print('Done fitting frame '+str(frame_index)+' of ' + str(metadata['sequence_count']))
            
        return self.result
            
        
    def main_loop(self, frame, frame_index):
        
        peaks = self.find_peaks(frame)
        peaks = peaks[peaks[:,2]> self.threshold]
        
        return self.fitter(frame_index, frame, peaks)
        
        
        
    def find_peaks(self, frame):
        kernel = np.array([[1,1,1],
                   [1,1,1],
                   [1,1,1]]) 
        
        out = signal.convolve2d(frame, kernel, boundary='fill', mode='same')/kernel.sum()
        
        row_min = self.ROI_size_1D
        row_max = frame.shape[0]-self.ROI_size_1D
        column_min = self.ROI_size_1D
        column_max = frame.shape[1]-self.ROI_size_1D
        
        maxima = np.zeros((frame.shape[0], frame.shape[1],8), dtype=bool)
        
        maxima[row_min:row_max,column_min:column_max,0] = out[row_min:row_max, column_min:column_max] > out[row_min:row_max,column_min+1:column_max+1]
        maxima[row_min:row_max,column_min:column_max,1] = out[row_min:row_max, column_min:column_max] >= out[row_min:row_max,column_min-1:column_max-1]
        maxima[row_min:row_max,column_min:column_max,2] = out[row_min:row_max, column_min:column_max] > out[row_min+1:row_max+1,column_min:column_max]
        maxima[row_min:row_max,column_min:column_max,3] = out[row_min:row_max, column_min:column_max] >= out[row_min-1:row_max-1,column_min:column_max]
        maxima[row_min:row_max,column_min:column_max,4] = out[row_min:row_max, column_min:column_max] >= out[row_min-1:row_max-1,column_min-1:column_max-1]
        maxima[row_min:row_max,column_min:column_max,5] = out[row_min:row_max, column_min:column_max] >= out[row_min-1:row_max-1,column_min+1:column_max+1]
        maxima[row_min:row_max,column_min:column_max,6] = out[row_min:row_max, column_min:column_max] > out[row_min+1:row_max+1,column_min-1:column_max-1]
        maxima[row_min:row_max,column_min:column_max,7] = out[row_min:row_max, column_min:column_max] >= out[row_min+1:row_max+1,column_min+1:column_max+1]
        
        mask = maxima.all(axis=2)
        mask = mask*self.ROI_zones
        indices = np.where(mask == True)
        indices = np.asarray([x for x in zip(indices[0],indices[1])])
        values = [[value] for value in frame[mask]]
        
        return np.append(indices,values, axis=1)
        
    
    def fitter(self, frame_index, frame, peaks):
        initX0 = 0
        Nfails = 0
        
        frame_result = np.zeros([peaks.shape[0], 12])
        
        for peak_index, peak in enumerate(peaks):
            myRow = int(peak[0])
            myColumn = int(peak[1])
            myROI = frame[myRow-self.ROI_size_1D:myRow+self.ROI_size_1D+1,myColumn-self.ROI_size_1D:myColumn+self.ROI_size_1D+1]
            #myROI_min = np.amin(myROI)
            myROI_bg = np.mean(np.append(np.append(np.append(myROI[:,0],myROI[:,-1]),np.transpose(myROI[0,1:-2])), np.transpose(myROI[-1,1:-2])))
            myROI = myROI - myROI_bg
            flagRow = False
            flagCol = False
            
            xx = np.transpose(range(-self.ROI_size_1D,self.ROI_size_1D+1))
            yy = np.transpose(range(-self.ROI_size_1D,self.ROI_size_1D+1))
            yRows = np.sum(myROI,axis=1)
            yCols = np.transpose(np.sum(myROI,axis=0))
            
            x0 = initX0
            sigX = self.initSig
            C = yCols[self.ROI_size_1D]
            for i in range(0,self.maxIts):
                fofX = C*np.exp(-np.square(xx-x0)/(2*sigX**2))
                beta = yCols - fofX
                A = np.vstack((fofX/C,fofX* (xx-x0/sigX**2),fofX*(np.square(xx-x0)/sigX**3)))
                b = np.matmul(A,beta)
                a = np.matmul(A,np.transpose(A))
                rc= np.linalg.cond(a)
                if math.isnan(rc) or rc < 1e-12:
                    residueCols = 0
                    break
                
                if abs(x0) > self.allowX or sigX < self.allowSig[0] or sigX > self.allowSig[1]:
                    residueCols = 0
                    break
            
                residueCols = np.sum(np.square(beta))/np.sum(np.square(yCols))
                if residueCols < self.mintol and abs(x0) < self.allowX and sigX > self.allowSig[0] and sigX < self.allowSig[1]:
                    break
                
                dL = np.matmul(a,1/b)
                C = C+dL[0]
                x0 = x0+dL[1]/10
                sigX = sigX +dL[2]/10
            
            if residueCols < self.maxtol and abs(x0) < self.allowX and sigX > self.allowSig[0] and sigX < self.allowSig[1]:
                fitColPos = float(myColumn) + x0 - 0.5
                flagCol = True
            
            if flagCol:
                y0 = initX0
                sigY = sigX
                C = yRows[self.ROI_size_1D]
                for j in range(0,self.maxIts):
                    fofX = C*np.exp(-np.square(yy-y0)/(2*sigY**2))
                    beta = yRows - fofX
                    A = np.vstack((fofX/C,fofX* (yy-y0/sigY**2),fofX*(np.square(yy-y0)/sigY**3)))
                    b = np.matmul(A,beta)
                    a = np.matmul(A,np.transpose(A))
                    rc= np.linalg.cond(a)
                    if math.isnan(rc) or rc < 1e-12:
                        residueRows = 0
                        break
                    
                    if abs(y0) > self.allowX or sigY < self.allowSig[0] or sigY > self.allowSig[1]:
                        residueRows = 0
                        break
                
                    residueRows = np.sum(np.square(beta))/np.sum(np.square(yRows))
                    if residueRows < self.mintol and abs(x0) < self.allowX and sigY > self.allowSig[0] and sigY < self.allowSig[1]:
                        break
                    
                    dL = np.matmul(a,1/b)
                    C = C+dL[0]
                    y0 = y0+dL[1]/10
                    sigY = sigY +dL[2]/10
                
                if residueRows < self.maxtol and abs(x0) < self.allowX and sigY > self.allowSig[0] and sigY < self.allowSig[1]:
                    fitRowPos = float(myRow) + y0 - 0.5
                    flagRow = True
                
            
            if flagRow and flagCol:
                frame_result[peak_index,0] = frame_index
                frame_result[peak_index,1] = peak_index
                frame_result[peak_index,2] = fitRowPos
                frame_result[peak_index,3] = fitColPos
                frame_result[peak_index,4] = peak[2]
                frame_result[peak_index,5] = sigY
                frame_result[peak_index,6] = sigX
                frame_result[peak_index,7] = (residueRows + residueCols) / 2
                frame_result[peak_index,8] = residueRows
                frame_result[peak_index,9] = residueCols
                frame_result[peak_index,10] = j
                frame_result[peak_index,11] = i
                
            else:
                Nfails +=1
                
        
        frame_result=frame_result[frame_result[:,4]>0]

        return frame_result
        
        
        


def MaxBergkamp():
    pass

