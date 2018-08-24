# GIBS Validation Slack Bot
Slack Bot for validating data in Global Imagery Browse Services ([GIBS](https://earthdata.nasa.gov/about/science-system-description/eosdis-components/global-imagery-browse-services-gibs)) Earth Satellite imagery. This Slack Bot is built using BotKit (HowdyAI) and Slacks Real-Time Messaging (RTM) Service. 

## Dependencies
Run ```npm install``` to install the various dependencies for the Node.js project.

## Running the Slack Bot ##
Find the bot token on Slack and enter the command below the run the Slack Bot on your machine.
```TOKEN=xoxb-your-token-here npm start```

In the Slack Channel, in a channel where the Slack Bot is a member, run
```@jeff-bot viirs_check [date_string] [layer_name]```

```
arguments:
 -- date_string 			Must be be "YYYY-MM-DD" or "today" to check yesterday
 -- layer_name (optional) 	Must be empty, "VIIRS_SNPP_CorrectedReflectance_TrueColor", "VIIRS_SNPP_CorrectedReflectance_BandsM3-I3-M11", or "VIIRS_SNPP_CorrectedReflectance_BandsM11-I2-I1"

```

## Node.js Interface
```index.js``` is the main JavaScript file which interacts with the Slack API and the ```validate_viirs.py``` Python script.

## Python Scripts
```validate_viirs.py``` is the main Python script which calls the helper functions below to download a GIBS test image, pre-process it, load a trained machine learning classifer, and report a result. 

Currently performs analysis on all VIIRS base layers for missing data and miscoloration. 

### Helper Files 
```gibs_layer.py``` contains a GIBS layer class with several predefined GIBS layers as well as the XML formats for [TMS and Tiled WMS](http://www.gdal.org/frmt_wms.html) services to request layers from the GIBS API using a gdal driver.

```utils.py``` contains various helper functions for PyTorch and date manipulation.

```features.py``` contains functions to featurize the image using histogram of oriented gradients (HoG) and color histogram descriptors using hue values.

```download_data.py``` downloads a GIBS layer dataset. The script uses [```gdal_translate```](http://www.gdal.org/gdal_translate.html) to query the [GIBS API](https://wiki.earthdata.nasa.gov/display/GIBS/GIBS+API+for+Developers#GIBSAPIforDevelopers-ServiceEndpointsandGetCapabilities). For our current purposes, we only use it to pull down a single image.
