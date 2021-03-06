#!/usr/bin/env python
###############################################################################
#  
#  Diabetes Data Guard (DD-Guard): BLE Broadcaster module
#  
#  Description:
#
#    The DD-Guard gateway module periodically receives real time data from the 
#    Medtronic Minimed 6XXG insulin pump and broadcasts the data using BLE Advertisements.
#  
#  Dependencies:
#
#    The project is a fork of Ondrej Wisniewski's ddguard project https://github.com/ondrej1024/ddguard.
#
#    DD-Guard uses the Python driver by paazan for the "Contour Next Link 2.4" 
#    radio bridge to the Minimed 670G to download real time data from the pump.
#    https://github.com/pazaan/decoding-contour-next-link
#    
#  Author:
#
#    Jan Henrik Holbek (jholbek@hotmail.com)
#  
#  Changelog:
#
#    11/02/2020 - example
#
#  TODO:
#    - Add read interval (syncing with the pump time to read every 5 mins)
#    - Add BLE broadcasting ()
#
#  Copyright 2020-2021, Jan Henrik Holbek
#  
#  This file is part of the DD-Guard project.
#  
#  DD-Guard is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
# 
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
# 
#  You should have received a copy of the GNU General Public License
#  along with crelay.  If not, see <http://www.gnu.org/licenses/>.
#  
###############################################################################

import signal
import syslog
import sys
import time
import thread
import ConfigParser
import cnl24driverlib
# import nightscoutlib
from sensor_codes import SENSOR_EXCEPTIONS

VERSION = "0.4.1"

UPDATE_INTERVAL = 300
MAX_RETRIES_AT_FAILURE = 3

sensor_exception_codes = {
    SENSOR_EXCEPTIONS.SENSOR_OK:               SENSOR_EXCEPTIONS.SENSOR_OK_STR,
    SENSOR_EXCEPTIONS.SENSOR_INIT:             SENSOR_EXCEPTIONS.SENSOR_INIT_STR,
    SENSOR_EXCEPTIONS.SENSOR_CAL_NEEDED:       SENSOR_EXCEPTIONS.SENSOR_CAL_NEEDED_STR,
    SENSOR_EXCEPTIONS.SENSOR_ERROR:            SENSOR_EXCEPTIONS.SENSOR_ERROR_STR,
    SENSOR_EXCEPTIONS.SENSOR_CAL_ERROR:        SENSOR_EXCEPTIONS.SENSOR_CAL_ERROR_STR,
    SENSOR_EXCEPTIONS.SENSOR_CHANGE_SENSOR:    SENSOR_EXCEPTIONS.SENSOR_CHANGE_SENSOR_STR,
    SENSOR_EXCEPTIONS.SENSOR_END_OF_LIFE:      SENSOR_EXCEPTIONS.SENSOR_END_OF_LIFE_STR,
    SENSOR_EXCEPTIONS.SENSOR_NOT_READY:        SENSOR_EXCEPTIONS.SENSOR_NOT_READY_STR,
    SENSOR_EXCEPTIONS.SENSOR_READING_HIGH:     SENSOR_EXCEPTIONS.SENSOR_READING_HIGH_STR,
    SENSOR_EXCEPTIONS.SENSOR_READING_LOW:      SENSOR_EXCEPTIONS.SENSOR_READING_LOW_STR,
    SENSOR_EXCEPTIONS.SENSOR_CAL_PENDING:      SENSOR_EXCEPTIONS.SENSOR_CAL_PENDING_STR,
    SENSOR_EXCEPTIONS.SENSOR_CHANGE_CAL_ERROR: SENSOR_EXCEPTIONS.SENSOR_CHANGE_CAL_ERROR_STR,
    SENSOR_EXCEPTIONS.SENSOR_TIME_UNKNOWN:     SENSOR_EXCEPTIONS.SENSOR_TIME_UNKNOWN_STR,
    SENSOR_EXCEPTIONS.SENSOR_LOST:             SENSOR_EXCEPTIONS.SENSOR_LOST_STR
}

is_connected = False

CONFIG_FILE = "/etc/ddguard.conf"


#########################################################
#
# Function:    read_config()
# Description: Read parameters from config file
# 
#########################################################
def read_config(cfilename):
   
   # Parameters from global config file
   config = ConfigParser.ConfigParser()
   config.read(cfilename)
   
   #TODO: check if file exists

   try:
      # Read Nightscout parameters
      read_config.nightscout_server     = config.get('nightscout', 'server').split("#")[0].strip('"').strip("'").strip()
      read_config.nightscout_api_secret = config.get('nightscout', 'api_secret').split("#")[0].strip('"').strip("'").strip()
   except ConfigParser.NoOptionError, ConfigParser.NoSectionError:
      syslog.syslog(syslog.LOG_ERR, "ERROR - Needed nightscout option not found in config file")
      return False

   try:
      # Read BGL parameters
      read_config.bgl_low_val      = int(config.get('bgl', 'bgl_low').split("#")[0].strip('"').strip("'"))
      read_config.bgl_pre_low_val  = int(config.get('bgl', 'bgl_pre_low').split("#")[0].strip('"').strip("'"))
      read_config.bgl_pre_high_val = int(config.get('bgl', 'bgl_pre_high').split("#")[0].strip('"').strip("'"))
      read_config.bgl_high_val     = int(config.get('bgl', 'bgl_high').split("#")[0].strip('"').strip("'"))
   except ConfigParser.NoOptionError, ConfigParser.NoSectionError:
      syslog.syslog(syslog.LOG_ERR, "ERROR - Needed bgl option not found in config file")
      return False

   print ("Nightscout server:     %s" % read_config.nightscout_server)
   print ("Nightscout api_secret: %s" % read_config.nightscout_api_secret)
   print
   print ("BGL low:      %d" % read_config.bgl_low_val)
   print ("BGL pre low:  %d" % read_config.bgl_pre_low_val)
   print ("BGL pre high: %d" % read_config.bgl_pre_high_val)
   print ("BGL high:     %d" % read_config.bgl_high_val)
   print
   return True



#########################################################
#
# Function:    on_sigterm()
# Description: signal handler for the TERM and INT signal
# 
#########################################################
def on_sigterm(signum, frame):

   try:
      # blynk.disconnect()
   except:
      pass
   syslog.syslog(syslog.LOG_NOTICE, "Exiting DD-Guard daemon")
   sys.exit()



#########################################################
#
# Function:    upload_live_data()
# Description: Read live data from pump and upload it 
#              to the enabled cloud services
#              This runs once at startup and then as a 
#              periodic timer every 5min
# 
#########################################################
def upload_live_data():
   
   # Guard against multiple threads
   if upload_live_data.active:
      return
    
   upload_live_data.active = True
   
   print "read live data from pump"
   hasFailed = True
   numRetries = MAX_RETRIES_AT_FAILURE
   while hasFailed and numRetries > 0:
      try:
         liveData = cnl24driverlib.readLiveData()
         hasFailed = False
      except:
         print "unexpected ERROR occured while reading live data"
         syslog.syslog(syslog.LOG_ERR, "Unexpected ERROR occured while reading live data")
         liveData = None
         numRetries -= 1
         if numRetries > 0:
            time.sleep(5)
    
   print(liveData)
   # TEST
   #liveData = {"actins":0.5, 
               #"bgl":778,
               #"time":"111",
               #"trend":2,
               #"unit":60,
               #"batt":25
              #}

   # Upload data to Nighscout server
   if nightscout != None:
      nightscout.upload(liveData)
    
   upload_live_data.active = False


##########################################################           
# Setup
##########################################################           

# read configuration parameters
if read_config(CONFIG_FILE) == False:
   sys.exit()

nightscout_enabled = (read_config.nightscout_server != "") and (read_config.nightscout_api_secret != "")

# Init Nighscout instance (if requested)
if nightscout_enabled:
   print "Nightscout upload is enabled"
   nightscout = nightscoutlib.nightscout_uploader(server = read_config.nightscout_server, 
                                                  secret = read_config.nightscout_api_secret)
else:
   nightscout = None

#### TODO: ANY PYTHON TIMER????
# Register timer function   
# timer = blynktimer.Timer()
# @timer.register(interval=5, run_once=True)
# @timer.register(interval=UPDATE_INTERVAL, run_once=False)
# def timer_function():
#     # Run this as separate thread so we don't cause ping timeouts
#     thread.start_new_thread(upload_live_data,())

   
##########################################################           
# Initialization
##########################################################           
syslog.syslog(syslog.LOG_NOTICE, "Starting DD-Guard daemon, version "+VERSION)

# Init signal handler
signal.signal(signal.SIGINT, on_sigterm)
signal.signal(signal.SIGTERM, on_sigterm)

upload_live_data.active = False


##########################################################           
# Main loop
##########################################################           
upload_live_data()
#while True:
#   timer.run() 
