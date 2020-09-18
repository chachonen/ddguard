import datetime
import struct
import time
from dateutil import tz
from bluetooth.ble import BeaconService


class BluetoothBroadcaster( object ):
    # Base time is midnight 1st Jan 2000 (UTC)
    baseTime = 946684800;
    epoch = datetime.datetime.utcfromtimestamp(0)

    def __init__( self ):
        # do something here

    def advertise_state( self, data ):
        str = ""
        str << data["timestamp"]
        str << "-"
        str << data["bgl"]
        str << "-"
        advertise(str)

    def advertise( self, string)
        service = BeaconService()
        service.start_advertising("11111111-2222-3333-4444-555555555555", 1, 1, 1, 200)
        time.sleep(15)
        service.stop_advertising()
