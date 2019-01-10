# Copyright 2018 California Institute of Technology.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os, sys
import pickle
import subprocess

import datetime
from datetime import datetime, time, date, timedelta

from features import *
from gibs_layer import GIBSLayer
import models.net as net
import utils

import numpy as np
from PIL import Image
import cv2

import torch
import torch.nn as nn
import torch.optim as optim
import torchvision.models as models
import torchvision.transforms as transforms
from torch.autograd import Variable

from sklearn.ensemble import RandomForestClassifier

# GIBS VIIRS Layer Definitions
VIIRS_SNPP_CorrectedReflectance_TrueColor = GIBSLayer.get_gibs_layer('VIIRS_SNPP_CorrectedReflectance_TrueColor')
VIIRS_SNPP_CorrectedReflectance_BandsM3_I3_M11 = GIBSLayer.get_gibs_layer('VIIRS_SNPP_CorrectedReflectance_BandsM3-I3-M11')
VIIRS_SNPP_CorrectedReflectance_BandsM11_I2_I1 = GIBSLayer.get_gibs_layer('VIIRS_SNPP_CorrectedReflectance_BandsM11-I2-I1')

viirs_layers = [VIIRS_SNPP_CorrectedReflectance_TrueColor, VIIRS_SNPP_CorrectedReflectance_BandsM3_I3_M11, VIIRS_SNPP_CorrectedReflectance_BandsM11_I2_I1]
img_size = (2048, 1024)
data_dir = 'data/4326/'

###############################################################################
# Parse Arguments from Slack Bot
###############################################################################

# TODO: Add Error Checking
datestring = sys.argv[1]
layer_name = sys.argv[2] if len(sys.argv) > 2 else ""
if layer_name in [layer.layer_name for layer in viirs_layers]:
    viirs_layers = [GIBSLayer.get_gibs_layer(layer_name)]
# print(datestring)

start_date = datestring
end_date = datetime.strptime(start_date, "%Y-%m-%d") + timedelta(1)
end_date = datetime.strftime(end_date, "%Y-%m-%d")

for layer in viirs_layers:
    layer_name = layer.layer_name
    img_extension = layer.format_suffix

    # Construct and resize the image
    filename = os.path.join(data_dir, datestring, layer_name + "." + img_extension)

    ###############################################################################
    # Download Image from Date
    ###############################################################################
    def run_command(cmd):
        """
        Runs the provided command on the terminal.
        Arguments:
            cmd: the command to be executed.
        """
        # print(cmd)
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        process.wait()
        for output in process.stdout:
            if b"ERROR" in output:
                raise Exception(error.strip())
        for error in process.stderr:
            raise Exception(error.strip())

    # Download the image if it does not exist
    if not os.path.isfile(filename):
        # Build up the command!
        cmd_list = ["python", "download_data.py", "--layer_name", layer_name,"--start_date", start_date, "--end_date", end_date]
        cmd = ' '.join(cmd_list)
        # print(cmd)

        # Run the command as a terminal subprocess
        try:
            run_command(cmd_list)
        except Exception as e:
          print(e)

    ###############################################################################
    # Miscoloration RF Classfier Stage
    ###############################################################################
    # load image from Disk
    test_image = np.asarray((Image.open(filename).resize(img_size, Image.BILINEAR)))

    # expand single image
    X_test = np.expand_dims(test_image, axis=0) # => (N x H x W x C)

    # featurize image
    num_color_bins = 360 # Number of bins in the color histogram
    feature_fns = [lambda img: color_histogram_hsv(img, nbin=num_color_bins)] #, hog_feature]
    X_test_feats = extract_features(X_test, feature_fns, verbose=False)

    # preprocess image
    mean_feats = np.load('models/random_forests/' + layer_name + '.npy')
    X_test_feats -= mean_feats

    # open the saved classifier file
    classifier_path = 'models/random_forests/' + layer_name + '.cpickle'
    with open(classifier_path, 'rb') as f:
        clf = pickle.load(f)

    # evaluate model on the image
    miscolor_test_prob = clf.predict_proba(X_test_feats)
    miscolor_test_pred = clf.predict(X_test_feats)

    # remove the batch index for the single image
    miscolor_test_prob = miscolor_test_prob[0]
    miscolor_test_pred = miscolor_test_pred[0]

    ###############################################################################
    # Missing Data CNN Classfier Stage
    ###############################################################################
    # Directory containing params.json
    model_dir = 'models/cnn'

    json_path = os.path.join(model_dir, 'params.json')
    assert os.path.isfile(json_path), "No json configuration file found at {}".format(json_path)
    params = utils.Params(json_path)

    # use GPU if available
    params.cuda = torch.cuda.is_available()
    # print("GPU available: {}".format(params.cuda))

    # set the random seed for reproducible experiments
    torch.manual_seed(230)
    if params.cuda: torch.cuda.manual_seed(230)

    # define the model
    num_classes = 2
    model = net.Net(params, num_classes=num_classes).cuda() if params.cuda else net.Net(params, num_classes=num_classes)

    # reload weights from the saved file
    map_location = None if params.cuda else 'cpu'
    saved_weights_filename = os.path.join(model_dir, layer_name + '.pth.tar')
    utils.load_checkpoint(saved_weights_filename, model, map_location=map_location)

    # set the model input size
    IMG_DIM = (128, 256)
    IMG_PADDING = (0, 64, 0, 64) # left, top, right, bottom borders

    # loader for evaluation, no data augmentation (e.g. horizontal flip)
    eval_transformer = transforms.Compose([
        transforms.Resize(IMG_DIM),  # resize the image
        transforms.Pad(padding=IMG_PADDING, fill=0), # pad to be square!
        transforms.Grayscale(),
        transforms.ToTensor(), # transform it into a torch tensor
        ])

    def image_loader(image_filename):
        """load image, returns cuda tensor"""
        image = np.asarray(Image.open(image_filename))

        # binarize image
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, image = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY)            
        image = Image.fromarray(image)

        # perform eval transforms
        image = eval_transformer(image).float()

        # move to GPU if available
        if params.cuda:
            image = image.cuda(async=True)

        # convert to Variable
        image = Variable(image, requires_grad=True)
        image = image.unsqueeze(0) # add batch dimension!

        return image

    # load the image
    image = image_loader(filename)

    # set model to evaluation mode
    model.eval() 
    output = model(image)

    # evaluate model on the image
    missing_test_prob = np.exp(output.data.cpu().numpy()) # exponentiate the log-probabilities
    missing_test_pred = np.argmax(missing_test_prob, axis=1)

    # remove the batch index for the single image
    missing_test_prob = missing_test_prob[0]
    missing_test_pred = missing_test_pred[0]

    ###############################################################################
    # Report Anomaly Found or Not!
    ###############################################################################
    NORMAL, ANOMALY = 0, 1

    print("{}".format(layer_name))
    if missing_test_pred == ANOMALY:
        print('- *ANOMALY (MISSING DATA)* detected with *{}%* confidence'.format(int(100*missing_test_prob[ANOMALY])))
    else:
        print('- *NORMAL (MISSING DATA)* predicted with *{}%* confidence'.format(int(100*missing_test_prob[NORMAL])))

    if miscolor_test_pred == ANOMALY:
        print('- *ANOMALY (MISCOLOR)* detected with *{}%* confidence'.format(int(100*miscolor_test_prob[ANOMALY])))
    else:
        print('- *NORMAL (MISCOLOR)* predicted with *{}%* confidence'.format(int(100*miscolor_test_prob[NORMAL])))

    ###############################################################################
    # Send Report Back to Slack Bot
    ###############################################################################
    image_url = 'https://gibs.earthdata.nasa.gov/wms/epsg4326/all/wms.cgi?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=${LAYER}&WIDTH=1024&HEIGHT=512&BBOX=-90,-180,90,180&CRS=epsg:4326&FORMAT=image/${FORMAT}&TIME=${DATE}'
    image_url = image_url.replace("${DATE}", datestring)
    image_url = image_url.replace("${FORMAT}", "png")
    image_url = image_url.replace("${LAYER}", layer_name)
    print(image_url)

    # Flush output!
    sys.stdout.flush()
