import scipy
import scipy.misc
import numpy as np
from PIL import Image
import os.path
import re
import os
import warnings
from distutils.version import LooseVersion
import shutil
import time
import glob
import mapillary_labels
import cv2
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from pylab import *              # Matplotlib's pylab interface
ion()                            # Turned on Matplotlib's interactive mode
from collections import deque

images_path_pattern = '../mapillary/data/train/*.jpg'
labels_path_pattern = '../mapillary/data/train/*.png'
verbose = False

desired_h = 1024
desired_w = 2048
desired_ratio = desired_w / desired_h
desired_top_crop_ratio = 0.66  # 1 = crop only top, 0 = crop only bottom, 0.5 = equal
assert desired_top_crop_ratio <= 1.0 and desired_top_crop_ratio >= 0.0


def change_color(fromimage, toimage, fromcolor, tocolor):
    r1, g1, b1 = fromcolor  # Original value
    red, green, blue = fromimage[:,:,0], fromimage[:,:,1], fromimage[:,:,2]
    mask = (red == r1) & (green == g1) & (blue == b1)
    toimage[mask] = tocolor
    # r2, g2, b2 = tocolor    # Value that we want to replace it with
    # toimage[:,:,:3][mask] = [r2, g2, b2]
    return np.sum(mask)

"""
def find_horizon(image, path):
    hls = cv2.cvtColor(image, cv2.COLOR_RGB2HLS)
    l = hls[:,:,1]
    print(l.shape)
    distribution = np.sum(l, axis=1)
    print(distribution.shape)
    print(distribution)
    figure(1, figsize=(6, 6))
    plt.plot(distribution)
    plt.ylabel('Distr.')
    plt.show()
    savefig(path)
    return
"""

# Find images to convert
image_paths = glob.glob(images_path_pattern)
label_paths = {re.sub('png', 'jpg', os.path.basename(path)): path for path in glob.glob(labels_path_pattern)}
assert len(image_paths) == len(label_paths)

# Used to estimate the remaining time
processing_times = deque([], maxlen=5)

for i, image_file in enumerate(image_paths):
    start_time = time.time()

    # Output filenames
    output_image_file = os.path.splitext(image_file)[0] + '_image.png'
    gt_image_file = label_paths[os.path.basename(image_file)]
    output_gt_image_file = os.path.splitext(gt_image_file)[0] + '_gt.png'
    # output_stats_file = os.path.splitext(gt_image_file)[0] + '_stats.png'

    # Read images
    image = scipy.misc.imread(image_file)
    gt_image = scipy.misc.imread(gt_image_file)

    print("({}/{}) Processing {} ({})...".format(i+1, len(image_paths), gt_image_file, gt_image.shape))

    # Crop both image and gt to be the desired_ratio
    h = gt_image.shape[0]
    w = gt_image.shape[1]
    ratio = w/h
    # find_horizon(image, output_stats_file)
    if ratio > desired_ratio:
        tocrop = int(w - h * desired_ratio)
        tocrop_left = int(0.5 * tocrop)
        w = w - tocrop
        #print("Need to crop horizontally, {}px per side".format(tocrop))
        image    =    image[0:h, tocrop_left:tocrop_left+w]
        gt_image = gt_image[0:h, tocrop_left:tocrop_left+w]
    elif ratio < desired_ratio:
        tocrop = int(h - w / desired_ratio)
        tocrop_top = int(desired_top_crop_ratio * tocrop)
        h = h - tocrop
        #print("Need to crop vertically, {}px per side".format(tocrop))
        image    =    image[tocrop_top:tocrop_top+h, 0:w]
        gt_image = gt_image[tocrop_top:tocrop_top+h, 0:w]
    else:
        pass
        #print("NO need to crop")
    #print(image.shape)
    #print(gt_image.shape)

    # Resize it to be desired_h * desired_w
    image_res = cv2.resize(image, (desired_w, desired_h), interpolation=cv2.INTER_NEAREST)
    gt_image_res = cv2.resize(gt_image, (desired_w, desired_h), interpolation=cv2.INTER_NEAREST)

    # Make sure the color image is 8 bit and create gt_image_bw output
    image = image.astype(dtype=np.uint8)
    gt_image_bw = np.zeros((gt_image_res.shape[0], gt_image_res.shape[1]), dtype=np.uint8)

    # Scroll through all possible labels and paint the output accordingly
    num_classes = len(mapillary_labels.labels)
    for c in range(num_classes):
        fromcolor = mapillary_labels.labels[c].color
        tocolor = mapillary_labels.labels[c].trainId
        n_changed_px = change_color(gt_image_res, gt_image_bw, fromcolor, tocolor)
        if verbose:
            print("    ({:5.2f}%)    RGB {:3}, {:3}, {:3} --> LABEL {:3}    {}".format(n_changed_px/gt_image_bw.size*100,
                                                                                fromcolor[0], fromcolor[1], fromcolor[2],
                                                                                tocolor,
                                                                                mapillary_labels.labels[i].name))

    # Save both the resized image and the gt image with B/W labelling
    scipy.misc.imsave(output_image_file, image_res)
    scipy.misc.imsave(output_gt_image_file, gt_image_bw)

    # Just check
    """
    check = scipy.misc.imread(output_gt_image_file)
    assert np.max(gt_image_bw) == np.max(check)
    """

    # Compute processing duration
    duration = time.time() - start_time
    processing_times.append(duration)
    avg_duration = np.mean(np.asarray(processing_times))
    remaining_time = int((len(image_paths) - (i+1)) * avg_duration)
    remaining_time_m, remaining_time_s = divmod(remaining_time, 60)
    remaining_time_h, remaining_time_m = divmod(remaining_time_m, 60)
    print("Remaining time: {:02d}:{:02d}:{:02d}".format(remaining_time_h, remaining_time_m, remaining_time_s))

