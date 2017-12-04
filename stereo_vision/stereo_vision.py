import numpy as np
import cv2
import os
from os.path import basename
import os.path
import glob
import time
import pickle
from collections import deque
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from moviepy.editor import VideoFileClip

import tty
import sys
import termios


"""
DOCUMENTATION

https://docs.opencv.org/2.4/modules/calib3d/doc/camera_calibration_and_3d_reconstruction.html
https://docs.opencv.org/3.0-beta/modules/calib3d/doc/camera_calibration_and_3d_reconstruction.html
https://github.com/opencv/opencv/blob/master/samples/python/stereo_match.py
MAYBE https://github.com/opencv/opencv/blob/master/samples/python/morphology.py

https://github.com/julienr/cvscripts/tree/master/rectification

BIBLE
https://github.com/tobybreckon/python-examples-cv/blob/master/stereo_sgbm.py

THE NEW TESTAMENT
https://github.com/erget/StereoVision
https://erget.wordpress.com/2014/02/01/calibrating-a-stereo-camera-with-opencv/

FILTERING
https://docs.opencv.org/3.1.0/d3/d14/tutorial_ximgproc_disparity_filtering.html

THE NEW MESSIAH
https://www.youtube.com/watch?v=MZsSTpS-XGI
ADCensus

"""


def write_ply(fn, verts, colors):
    ply_header = '''ply
                    format ascii 1.0
                    element vertex %(vert_num)d
                    property float x
                    property float y
                    property float z
                    property uchar red
                    property uchar green
                    property uchar blue
                    end_header
                    '''
    verts = verts.reshape(-1, 3)
    colors = colors.reshape(-1, 3)
    verts = np.hstack([verts, colors])
    with open(fn, 'wb') as f:
        f.write((ply_header % dict(vert_num=len(verts))).encode('utf-8'))
        np.savetxt(f, verts, fmt='%f %f %f %d %d %d ')


class BMTuner():
    """
    https://docs.opencv.org/2.4.1/modules/calib3d/doc/camera_calibration_and_3d_reconstruction.html
    """

    def __init__(self, undistorted_rectifiedL, undistorted_rectifiedR, undistorted_rectified_background):
        # Matcher
        window_size = 5
        self.minDisparity = 0
        self.numDisparities = 128
        self.blockSize = window_size  # old SADWindowSize
        self.P1 = 8 * 3 * window_size**2
        self.P2 = 32 * 3 * window_size**2
        self.disp12MaxDiff = 1
        self.uniquenessRatio = 10
        self.speckleWindowSize = 100
        self.speckleRange = 32
        self.preFilterCap = 31

        # Filter
        self.wls_lambda = 100000
        self.wls_sigma = 0.8

        # Input images
        self.undistorted_rectifiedL = undistorted_rectifiedL
        self.undistorted_rectifiedR = undistorted_rectifiedR
        self.undistorted_rectified_background = undistorted_rectified_background
        self.grayL = cv2.cvtColor(self.undistorted_rectifiedL, cv2.COLOR_BGR2GRAY)
        self.grayR = cv2.cvtColor(self.undistorted_rectifiedR, cv2.COLOR_BGR2GRAY)

        # Disparity crop
        self.crop_left = 100
        self.crop_right = -100
        self.crop_top = 0
        self.crop_bottom = 700
        
        # Create window
        self.windowNameD = "SGBM Stereo Disparity"
        cv2.namedWindow(self.windowNameD, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.windowNameD, 1200, 1000)
        cv2.moveWindow(self.windowNameD, 0, 0)
        cv2.createTrackbar("change_minDisparity", self.windowNameD, self.minDisparity, 100, self.change_minDisparity)
        cv2.createTrackbar("change_numDisparities (*16)", self.windowNameD, int(self.numDisparities/16), 16, self.change_numDisparities)
        cv2.createTrackbar("change_blockSize", self.windowNameD, self.blockSize, 21, self.change_blockSize)
        cv2.createTrackbar("change_P1", self.windowNameD, self.P1, 10000, self.change_P1)
        cv2.createTrackbar("change_P2", self.windowNameD, self.P2, 10000, self.change_P2)
        cv2.createTrackbar("change_disp12MaxDiff", self.windowNameD, self.disp12MaxDiff, 100, self.change_disp12MaxDiff)
        cv2.createTrackbar("change_uniquenessRatio", self.windowNameD, self.uniquenessRatio, 100, self.change_uniquenessRatio)
        cv2.createTrackbar("change_speckleWindowSize", self.windowNameD, self.speckleWindowSize, 1000, self.change_speckleWindowSize)
        cv2.createTrackbar("change_speckleRange", self.windowNameD, self.speckleRange, 100, self.change_speckleRange)
        cv2.createTrackbar("change_preFilterCap", self.windowNameD, self.preFilterCap, 100, self.change_preFilterCap)
        cv2.createTrackbar("change_wls_lambda (/1000)", self.windowNameD, int(self.wls_lambda/1000), 1000000, self.change_wls_lambda)
        cv2.createTrackbar("change_wls_sigma (/10)", self.windowNameD, int(self.wls_sigma*10), 40, self.change_wls_sigma)
        cv2.setMouseCallback(self.windowNameD, self.save_cloud_function)  # Right click on the image to save the point cloud
        
        # Run the first time
        self.refreshBM()
        
        while 1:
            k = cv2.waitKey()
            if k == 27:
                break
            
        
    def refreshBM(self):
        matcherL = cv2.StereoSGBM_create(minDisparity=self.minDisparity,
                                         numDisparities=self.numDisparities,
                                         blockSize=self.blockSize,
                                         P1=self.P1,
                                         P2=self.P2,
                                         disp12MaxDiff=self.disp12MaxDiff,
                                         uniquenessRatio=self.uniquenessRatio,
                                         speckleWindowSize=self.speckleWindowSize,
                                         speckleRange=self.speckleRange,
                                         preFilterCap=self.preFilterCap
                                         )

        matcherR = cv2.ximgproc.createRightMatcher(matcherL)

        use_wls_filter = 1
        if use_wls_filter:
            # Filter parameters
            visual_multiplier = 1.0
            wls_filter = cv2.ximgproc.createDisparityWLSFilter(matcher_left=matcherL)
            wls_filter.setLambda(self.wls_lambda)
            wls_filter.setSigmaColor(self.wls_sigma)

        # Calculate disparity (return a fixed-point disparity map, where disparity values are multiplied by 16)
        disparityL = matcherL.compute(self.grayL, self.grayR)

        if use_wls_filter:
            # Filtered
            disparityR = matcherR.compute(self.grayR, self.grayL)
            disparity_filtered = wls_filter.filter(np.int16(disparityL / 16.), self.undistorted_rectifiedL, None, np.int16(disparityR / 16.))
            disparity_filtered = cv2.normalize(src=disparity_filtered, dst=disparity_filtered, beta=0, alpha=255, norm_type=cv2.NORM_MINMAX)
            disparity_filtered = np.uint8(disparity_filtered)
            self.disparity_scaled = disparity_filtered
        else:
            # Unfiltered
            # cv2.filterSpeckles(disparityL, 0, 4000, 128)
            self.disparity_scaled = (disparityL / 16.).astype(np.uint8) + abs(disparityL.min())

        #B = 200  # distance between images, in mm
        #f = 10  # focal length, in px?
        #z = B * f / self.disparity

        # Crop
        self.disparity_scaled = self.disparity_scaled[self.crop_top:self.crop_bottom,self.crop_left:self.crop_right]
        self.disparity_size = self.disparity_scaled.shape
        
        # Write on image
        preview = self.disparity_scaled.copy()
        interline_px = 35
        text = 'minDisparity: {}'.format(self.minDisparity)
        cv2.putText(preview, text, (10,25+0*interline_px), cv2.FONT_HERSHEY_SIMPLEX, 1, 255, 2, 8)
        text = 'numDisparities: {}'.format(self.numDisparities)
        cv2.putText(preview, text, (10,25+1*interline_px), cv2.FONT_HERSHEY_SIMPLEX, 1, 255, 2, 8)
        text = 'blockSize: {}'.format(self.blockSize)
        cv2.putText(preview, text, (10,25+2*interline_px), cv2.FONT_HERSHEY_SIMPLEX, 1, 255, 2, 8)
        text = 'P1: {}'.format(self.P1)
        cv2.putText(preview, text, (10,25+3*interline_px), cv2.FONT_HERSHEY_SIMPLEX, 1, 255, 2, 8)
        text = 'P2: {}'.format(self.P2)
        cv2.putText(preview, text, (10,25+4*interline_px), cv2.FONT_HERSHEY_SIMPLEX, 1, 255, 2, 8)
        text = 'disp12MaxDiff: {}'.format(self.disp12MaxDiff)
        cv2.putText(preview, text, (10,25+5*interline_px), cv2.FONT_HERSHEY_SIMPLEX, 1, 255, 2, 8)
        text = 'uniquenessRatio: {}'.format(self.uniquenessRatio)
        cv2.putText(preview, text, (10,25+6*interline_px), cv2.FONT_HERSHEY_SIMPLEX, 1, 255, 2, 8)
        text = 'speckleWindowSize: {}'.format(self.speckleWindowSize)
        cv2.putText(preview, text, (10,25+7*interline_px), cv2.FONT_HERSHEY_SIMPLEX, 1, 255, 2, 8)
        text = 'speckleRange: {}'.format(self.speckleRange)
        cv2.putText(preview, text, (10,25+8*interline_px), cv2.FONT_HERSHEY_SIMPLEX, 1, 255, 2, 8)
        text = 'preFilterCap: {}'.format(self.preFilterCap)
        cv2.putText(preview, text, (10,25+9*interline_px), cv2.FONT_HERSHEY_SIMPLEX, 1, 255, 2, 8)
        text = 'wls_lambda: {}'.format(self.wls_lambda)
        cv2.putText(preview, text, (10,25+10*interline_px), cv2.FONT_HERSHEY_SIMPLEX, 1, 255, 2, 8)
        text = 'wls_sigma: {}'.format(self.wls_sigma)
        cv2.putText(preview, text, (10,25+11*interline_px), cv2.FONT_HERSHEY_SIMPLEX, 1, 255, 2, 8)

        # Display disparity
        cv2.imshow(self.windowNameD, preview)

    def change_minDisparity(self, value):
        self.minDisparity = value
        self.refreshBM()
        
    def change_numDisparities(self, value):
        self.numDisparities = value * 16
        self.refreshBM()
        
    def change_blockSize(self, value):
        if value > 2 and value < 22 and value%2 == 1:
            self.blockSize = value
            self.refreshBM()
        
    def change_P1(self, value):
        self.P1 = value
        self.refreshBM()
        
    def change_P2(self, value):
        self.P2 = value
        self.refreshBM()
    
    def change_disp12MaxDiff(self, value):
        self.disp12MaxDiff = value
        self.refreshBM()
    
    def change_uniquenessRatio(self, value):
        self.uniquenessRatio = value
        self.refreshBM()
    
    def change_speckleWindowSize(self, value):
        self.speckleWindowSize = value
        self.refreshBM()
    
    def change_speckleRange(self, value):
        self.speckleRange = value
        self.refreshBM()
    
    def change_preFilterCap(self, value):
        self.preFilterCap = value
        self.refreshBM()

    def change_wls_lambda(self, value):
        self.wls_lambda = value * 1000
        self.refreshBM()

    def change_wls_sigma(self, value):
        self.wls_sigma = value / 10
        self.refreshBM()

    # Save cloud
    def save_cloud_function(self, event, x, y, flags, param):
        if event == cv2.EVENT_RBUTTONDOWN:
            basename = 'disparity'
            h, w = imgL.shape[:2]
            f = 0.8*w                          # guess for focal length
            Q = np.float32([[1, 0, 0, -0.5*w],
                            [0,-1, 0,  0.5*h], # turn points 180 deg around x-axis,
                            [0, 0, 0,     -f], # so that y-axis looks up
                            [0, 0, 1,      0]])
            points = cv2.reprojectImageTo3D(self.disparity_scaled, Q)
            #colors = cv2.cvtColor(imgL, cv2.COLOR_BGR2RGB)   # I don't think it makes sense, as the disparity is calculated on the remapped image not on imgL
            colors = cv2.cvtColor(self.undistorted_rectified_background,
                                  cv2.COLOR_BGR2RGB)
            colors = colors[self.crop_top:self.crop_bottom,self.crop_left:self.crop_right]
            mask = self.disparity_scaled > self.disparity_scaled.min()
            out_points = points[mask]
            out_colors = colors[mask]
            while os.path.isfile(basename + '.ply'):
                basename = basename + '_'
            print("Saving point cloud as {}".format(basename + '.ply'))
            write_ply(basename + '.ply', out_points, out_colors)
            print("Done")


class Calibration():
    def __init__(self, path, left_template, right_template, toskip=[], save=False):
        
        # Paths
        self.path = path
        self.save = save
    
        # Load filenames for images
        self.imagesL = glob.glob(self.path + left_template)
        self.imagesR = glob.glob(self.path + right_template)
        self.imagesL.sort()
        self.imagesR.sort()
        assert len(self.imagesL) == len(self.imagesR)
        n_before = len(self.imagesL)

        # Removing the ones manually specified as unsuitable
        # This won't work if the template is not the standard one. Modify manually in case.
        for i in toskip:
            sL = self.path + "left_{:03d}.png".format(i)
            sR = self.path + "right_{:03d}.png".format(i)
            if sL in self.imagesL:
                self.imagesL.remove(sL)
                self.imagesR.remove(sR)
        self.imagesL.sort()
        self.imagesR.sort()
        assert len(self.imagesL) == len(self.imagesR)
        n_after = len(self.imagesL)
        print("{} images loaded, {} remaining after manual selection".format(n_before, n_after))

        # Termination criteria
        self.termination_criteria_subpix = (cv2.TERM_CRITERIA_EPS +
                                            cv2.TERM_CRITERIA_MAX_ITER,
                                            30,
                                            0.001)
        self.termination_criteria_extrinsics = (cv2.TERM_CRITERIA_EPS +
                                                cv2.TERM_CRITERIA_MAX_ITER,
                                                100,
                                                0.001)      # chubby guy: 1e-5

        # Pattern specs
        self.patternX = 6
        self.patternY = 9
        self.square_size_in_mm = 40

        # Arrays to store object points and image points from all the images
        self.objpoints = [] # 3d point in real world space
        self.imgpointsR = [] # 2d points in image plane
        self.imgpointsL = [] # 2d points in image plane
        self.image_size = None

        # Filenames
        self.calibration = None
        self.calibration_filename = "calibration.p"

        # Windows
        self.windowNameL = "LEFT Camera"
        self.windowNameR = "RIGHT Camera"
        self.ratio = 1920/1208
        self.wsize = 800
        cv2.namedWindow(self.windowNameL, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.windowNameL, self.wsize, int(self.wsize/self.ratio))
        cv2.moveWindow(self.windowNameL, 0, 0)
        cv2.namedWindow(self.windowNameR, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self.windowNameR, self.wsize, int(self.wsize/self.ratio))
        cv2.moveWindow(self.windowNameR, self.wsize+100, 0)


    def calibrate(self, visual=False, window_timeout=500):
        
        """
        Intrinsic parameters
        """
        # prepare object points, like (0,0,0), (1,0,0), (2,0,0) ....,(6,5,0)
        objp = np.zeros((self.patternX*self.patternY,3), np.float32)
        objp[:,:2] = np.mgrid[0:self.patternX,0:self.patternY].T.reshape(-1,2)
        objp = objp * self.square_size_in_mm

        # count number of chessboard detection (across both images)
        chessboard_pattern_detections = 0
        chessboard_pattern_detections_accepted = 0

        for i in range(len(self.imagesL)):
            imgL = cv2.imread(self.imagesL[i])
            imgR = cv2.imread(self.imagesR[i])
            grayL = cv2.cvtColor(imgL, cv2.COLOR_BGR2GRAY)
            grayR = cv2.cvtColor(imgR, cv2.COLOR_BGR2GRAY)
            self.image_size = grayL.shape[::-1]

            # Find the chess board corners
            flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE #| cv2.CALIB_CB_FAST_CHECK
            retR, cornersL = cv2.findChessboardCorners(imgL, (self.patternX, self.patternY), flags)
            retL, cornersR = cv2.findChessboardCorners(imgR, (self.patternX, self.patternY), flags)

            if retR and retL:
                chessboard_pattern_detections += 1

                # refine corner locations to sub-pixel accuracy and then
                corners_sp_L = cv2.cornerSubPix(grayL, cornersL, (11,11), (-1,-1), self.termination_criteria_subpix)
                corners_sp_R = cv2.cornerSubPix(grayR, cornersR, (11,11), (-1,-1), self.termination_criteria_subpix)

                # Draw and display the corners
                drawboardL = cv2.drawChessboardCorners(imgL, (self.patternX, self.patternY), corners_sp_L, retL)
                drawboardR = cv2.drawChessboardCorners(imgR, (self.patternX, self.patternY), corners_sp_R, retR)

                if visual:
                    text = 'Image {}: detecting chessboard pattern'.format(self.imagesL[i])
                    cv2.putText(drawboardL, text, (10,25), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2, 8)
                    text = 'Image {}: detecting chessboard pattern'.format(self.imagesR[i])
                    cv2.putText(drawboardR, text, (10,25), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2, 8)
                    cv2.imshow(self.windowNameL, drawboardL)
                    cv2.imshow(self.windowNameR, drawboardR)
                    key = cv2.waitKey(window_timeout)

                # Add to global list
                self.imgpointsL.append(corners_sp_L)
                self.imgpointsR.append(corners_sp_R)
                self.objpoints.append(objp)
                chessboard_pattern_detections_accepted += 1

        print("Total number of accepted images: {}".format(chessboard_pattern_detections_accepted))

        # Perform calibration on both cameras - uses [Zhang, 2000]
        ret, self.mtxL, self.distL, self.rvecsL, self.tvecsL = cv2.calibrateCamera(self.objpoints, self.imgpointsL, self.image_size, None, None)
        ret, self.mtxR, self.distR, self.rvecsR, self.tvecsR = cv2.calibrateCamera(self.objpoints, self.imgpointsR, self.image_size, None, None)

        # Check results
        if visual:
            for i in range(len(self.imagesL)):
                imgL = cv2.imread(self.imagesL[i])
                imgR = cv2.imread(self.imagesR[i])
                undistortedL = cv2.undistort(imgL, self.mtxL, self.distL, None, None)
                undistortedR = cv2.undistort(imgR, self.mtxR, self.distR, None, None)
                text = 'Image {}: this should be undistorted'.format(self.imagesL[i])
                cv2.putText(undistortedL, text, (10,25), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2, 8)
                text = 'Image {}: this should be undistorted'.format(self.imagesR[i])
                cv2.putText(undistortedR, text, (10,25), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2, 8)
                cv2.imshow(self.windowNameL, undistortedL);
                cv2.imshow(self.windowNameR, undistortedR);
                key = cv2.waitKey(window_timeout)
            
        # Show mean re-projection error of the object points onto the image(s)
        tot_errorL = 0
        for i in range(len(self.objpoints)):
            imgpointsL2, _ = cv2.projectPoints(self.objpoints[i], self.rvecsL[i], self.tvecsL[i], self.mtxL, self.distL)
            errorL = cv2.norm(self.imgpointsL[i], imgpointsL2, cv2.NORM_L2)/len(imgpointsL2)
            tot_errorL += errorL
        print("LEFT: Re-projection error: ", tot_errorL/len(self.objpoints))

        tot_errorR = 0
        for i in range(len(self.objpoints)):
            imgpointsR2, _ = cv2.projectPoints(self.objpoints[i], self.rvecsR[i], self.tvecsR[i], self.mtxR, self.distR)
            errorR = cv2.norm(self.imgpointsR[i],imgpointsR2, cv2.NORM_L2)/len(imgpointsR2)
            tot_errorR += errorR
        print("RIGHT: Re-projection error: ", tot_errorR/len(self.objpoints))

        """
        Extrinsic parameters
        """
        # this takes the existing calibration parameters used to undistort the individual images as
        # well as calculated the relative camera positions - represented via the fundamental matrix, F
        # alter termination criteria to (perhaps) improve solution - ?
        
        # Set flags (chubby)
        flags = 0
        flags |= cv2.CALIB_FIX_INTRINSIC
        # flags |= cv2.CALIB_FIX_PRINCIPAL_POINT
        flags |= cv2.CALIB_USE_INTRINSIC_GUESS
        flags |= cv2.CALIB_FIX_FOCAL_LENGTH
        # flags |= cv2.CALIB_FIX_ASPECT_RATIO
        flags |= cv2.CALIB_ZERO_TANGENT_DIST
        # flags |= cv2.CALIB_RATIONAL_MODEL
        # flags |= cv2.CALIB_SAME_FOCAL_LENGTH
        # flags |= cv2.CALIB_FIX_K3
        # flags |= cv2.CALIB_FIX_K4
        # flags |= cv2.CALIB_FIX_K5
        
        rms_stereo, \
        self.camera_matrix_l, \
        self.dist_coeffs_l, \
        self.camera_matrix_r, \
        self.dist_coeffs_r, \
        self.R, \
        self.T, \
        self.E, \
        self.F = cv2.stereoCalibrate(self.objpoints, self.imgpointsL, self.imgpointsR,
                                     self.mtxL,
                                     self.distL,
                                     self.mtxR,
                                     self.distR,
                                     self.image_size,
                                     criteria=self.termination_criteria_extrinsics,
                                     flags=0)
        
        print("Stereo RMS left to right re-projection error: {}".format(rms_stereo))

        """
        Rectification
        """        
        RL, RR, PL, PR, Q, _, _ = cv2.stereoRectify(self.camera_matrix_l,
                                                    self.dist_coeffs_l,
                                                    self.camera_matrix_r,
                                                    self.dist_coeffs_r,
                                                    self.image_size,
                                                    self.R,
                                                    self.T)

        # compute the pixel mappings to the rectified versions of the images
        self.mapL1, self.mapL2 = cv2.initUndistortRectifyMap(self.camera_matrix_l, self.dist_coeffs_l, RL, PL, self.image_size, cv2.CV_32FC1)
        self.mapR1, self.mapR2 = cv2.initUndistortRectifyMap(self.camera_matrix_r, self.dist_coeffs_r, RR, PR, self.image_size, cv2.CV_32FC1)
        print(self.image_size)

        # Check rectification
        if visual:
            for i in range(len(self.imagesL)):
                imgL = cv2.imread(self.imagesL[i])
                imgR = cv2.imread(self.imagesR[i])
                undistorted_rectifiedL = cv2.remap(imgL, self.mapL1, self.mapL2, cv2.INTER_LINEAR)
                undistorted_rectifiedR = cv2.remap(imgR, self.mapR1, self.mapR2, cv2.INTER_LINEAR)
                text = 'Image {}: this should be undistorted and rectified'.format(self.imagesL[i])
                cv2.putText(undistorted_rectifiedL, text, (10,25), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2, 8)
                text = 'Image {}: this should be undistorted and rectified'.format(self.imagesR[i])
                cv2.putText(undistorted_rectifiedR, text, (10,25), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2, 8)
                cv2.imshow(self.windowNameL, undistorted_rectifiedL)
                cv2.imshow(self.windowNameR, undistorted_rectifiedR)
                key = cv2.waitKey(window_timeout)

        cv2.destroyAllWindows()

        # Save
        if self.save:
            self.calibration = { "mapL1": self.mapL1,
                                 "mapL2": self.mapL2,
                                 "mapR1": self.mapR1,
                                 "mapR2": self.mapR2 }
            pickle.dump(self.calibration, open(self.path + self.calibration_filename, "wb"))

        return


    def calculate_depth(self, calibration, imgL, imgR, imgB, save_intermediate=False):
        # uses a modified H. Hirschmuller algorithm [HH08] that differs (see opencv manual)
        # parameters can be adjusted, current ones from [Hamilton / Breckon et al. 2013]
        
        # FROM manual: stereoProcessor = cv2.StereoSGBM(numDisparities=128, SADWindowSize=21);
        # From help(cv2): StereoBM_create(...)
        #        StereoBM_create([, numDisparities[, blockSize]]) -> retval
        #
        #    StereoSGBM_create(...)
        #        StereoSGBM_create(minDisparity, numDisparities, blockSize[, P1[, P2[,
        # disp12MaxDiff[, preFilterCap[, uniquenessRatio[, speckleWindowSize[, speckleRange[, mode]]]]]]]]) -> retval

        
        # undistort and rectify based on the mappings (could improve interpolation and image border settings here)
        # N.B. mapping works independant of number of image channels
        undistorted_rectifiedL = cv2.remap(imgL, calibration["mapL1"], calibration["mapL2"], interpolation=cv2.INTER_LINEAR)
        undistorted_rectifiedR = cv2.remap(imgR, calibration["mapR1"], calibration["mapR2"], interpolation=cv2.INTER_LINEAR)
        undistorted_rectified_background = cv2.remap(imgB, calibration["mapR1"], calibration["mapR2"], interpolation=cv2.INTER_LINEAR)
        if save_intermediate:
            cv2.imwrite("intermediate_left.png", undistorted_rectifiedL)
            cv2.imwrite("intermediate_right.png", undistorted_rectifiedR)
        cv2.imshow(self.windowNameL, undistorted_rectifiedL)
        cv2.imshow(self.windowNameR, undistorted_rectifiedR)

        tuner = BMTuner(undistorted_rectifiedL, undistorted_rectifiedR, undistorted_rectified_background)

        """
                key = cv2.waitKey(0)
                cv2.destroyAllWindows()
        """
        return


if __name__ == '__main__':

    calibration_folder = '../videos/20171201_stereo_TMG/calibration_frames/'
    toskip = []
    test_folder = '../videos/20171201_stereo_TMG/test_frames/'
    segmented_test_folder = '../videos/20171201_stereo_TMG/test_frames_segmented/'
    CALIBRATE = 0
    TEST = 1

    cameras = Calibration(calibration_folder,
                          toskip=toskip,
                          left_template='calibration_left_*_cropped.png',
                          right_template='calibration_right_*_cropped.png',
                          save=True)

    if CALIBRATE:
        cameras.calibrate(visual=True)

    if TEST:
        mycal = pickle.load(open(calibration_folder + "calibration.p", "rb"))
        fileL = test_folder + 'test_left_013_cropped.png'
        fileR = test_folder + 'test_right_013_cropped.png'
        fileB = segmented_test_folder + 'test_left_013_cropped.png'
        imgL = cv2.imread(fileL)
        imgR = cv2.imread(fileR)
        imgB = cv2.imread(fileB)
        imgB = cv2.resize(imgB, (1440, 896))# (320, 512)
        cameras.calculate_depth(mycal,
                                imgL, imgR,
                                imgB,
                                save_intermediate=1)

