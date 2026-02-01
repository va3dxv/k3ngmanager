#!/usr/local/bin/python3.11
#pyinstaller --onefile --windowed --icon=icon.ico -F k3ngmanager.py
import wx
import wx.grid
from operator import itemgetter
import os
import time
import requests
import serial
import serial.tools.list_ports
from wx.lib.embeddedimage import PyEmbeddedImage
from threading import Thread
import json
from datetime import datetime, timezone
from sgp4.api import Satrec, days2mdhms
from astropy.coordinates import TEME, ITRS, CartesianDifferential, CartesianRepresentation
from astropy import units as u
from astropy.time import Time
from pytz import timezone

class MainPanel(wx.Panel):
    def __init__(self, parent, color, size):
        wx.Panel.__init__(self, parent=parent)
        self.parent=parent
        self.color=color
        self.SetSize(size)
        self.SetMinSize(size=(size))
        self.SetMaxSize(size=(size))
        self.amsaturl = 'https://www.amsat.org/tle/current/nasabare.txt'
        self.tleurl = 'https://db.satnogs.org/api/tle/'
        self.radiourl = 'https://db.satnogs.org/api/transmitters/'
        self.saturl = 'https://db.satnogs.org/api/satellites/'
        self.cmdrefurl = 'https://raw.githubusercontent.com/wiki/k3ng/k3ng_rotator_controller/820-Command-Reference.md'
        self.userhome = os.getenv('USERPROFILE')
        self.apphome = f'{self.userhome}\\AppData\\Roaming\\k3ngmanager'
        self.skyroofsatfile = f'{self.userhome}\\AppData\\Roaming\\Afreet\\Products\\SkyRoof\\Satellites.json'
        self.skyroofsettings = f'{self.userhome}\\AppData\\Roaming\\Afreet\\Products\\SkyRoof\\Settings.json'
        if os.path.isdir(self.apphome) == False:
            os.makedirs(self.apphome)
        self.satfile = f'{self.apphome}\\autosave.tle'
        self.satnames = [] # satellite names for drop down selection
        self.selectedsats = [] # list of satellite dictionaries currently selected
        self.satlist = [] # list of all satellite dictionaries
        self.comports = {} # com ports dictionary
        self.portslist = [] # list of com ports for drop down
        self.speedslist = ['1200','2400','4800','9600','14400','19200','38400','57600','115200']
        for comport in serial.tools.list_ports.comports():
            self.comports[comport.description] = comport.device
            self.portslist.append(comport.description)

        self.cmddict = {
            'Enable/Disable Debug': '\D', 
            'Park Antenna': '\P',
            'Query Clock': '\?CL', 
            'GPS Sync Status': '\?GS',
            'Query GPS Location': '\?RC', 
            'Query AZ/EL Position': 'C2', 
            'Print Loaded Sats': '\@', 
            'Erase Loaded Sats': '\!', 
            'Re-calc Sats': '\&', 
            'Ping Remote': '\PG', 
            'Query AZ Start': '\I', 
            'Query AZ Capability': '\J', 
            'Stop All Rotation': '\?SS',
            'Save EEPROM and restart': '\Q',
            }
        self.cmdlist = list(self.cmddict.keys())
        self.connected = False
        self.debugon = False
        self.tracking = False
        self.skyroofpresent = False
        self.getbutton = wx.Button(self, label='Fetch TLE\'s From Internet', pos=(20,5), size=(160,25))
        self.getbutton.Bind(wx.EVT_BUTTON, self.getSats, self.getbutton, id=self.getbutton.GetId())

        self.updatebutton = wx.Button(self, label='Update TLE List', pos=(20,5), size=(160,25))
        self.updatebutton.Bind(wx.EVT_BUTTON, self.updateTLEs, self.updatebutton, id=self.updatebutton.GetId())
        self.updatebutton.Hide()

        self.loadbutton = wx.Button(self, label='Load a Saved List', pos=(190,5), size=(110,25))
        self.loadbutton.Bind(wx.EVT_BUTTON, self.loadFile, self.loadbutton, id=self.loadbutton.GetId())

        self.savebutton = wx.Button(self, label='Save this List', pos=(310,5), size=(110,25))
        self.savebutton.Bind(wx.EVT_BUTTON, self.saveFile, self.savebutton, id=self.savebutton.GetId())

        self.clearbutton = wx.Button(self, label='Clear', pos=(815,5), size=(80,25))
        self.clearbutton.Bind(wx.EVT_BUTTON, self.clearSel, self.clearbutton, id=self.clearbutton.GetId())

        self.exitbutton = wx.Button(self, label='Exit', pos=(900,5), size=(80,25))
        self.exitbutton.Bind(wx.EVT_BUTTON, self.exit, self.exitbutton, id=self.exitbutton.GetId())

        wx.StaticText(self, -1, 'Pick a Satellite: ', pos=(15,42))
        self.satchoice = wx.Choice(self, choices=self.satnames, pos=(100,40), size=(140,25))

        self.addbutton = wx.Button(self, label='Add to List', pos=(245,40), size=(80,25))
        self.addbutton.Bind(wx.EVT_BUTTON, self.selectSat, self.addbutton, id=self.addbutton.GetId())
        self.addbutton.Disable()

        wx.StaticText(self, -1, 'COM Port: ', pos=(490,42))
        self.portchoice = wx.Choice(self, choices=self.portslist, pos=(550,40), size=(220,25))

        wx.StaticText(self, -1, 'Baudrate: ', pos=(775,42))
        self.speedchoice = wx.Choice(self, choices=self.speedslist, pos=(830,40))

        self.connectbutton = wx.Button(self, label='Connect', pos=(900,40), size=(80,25))
        self.connectbutton.Bind(wx.EVT_BUTTON, self.serialConnect, self.connectbutton, id=self.connectbutton.GetId())

        self.disconnectbutton = wx.Button(self, label='Disconnect', pos=(900,40), size=(80,25))
        self.disconnectbutton.Bind(wx.EVT_BUTTON, self.serialDisconnect, self.disconnectbutton, id=self.disconnectbutton.GetId())
        self.disconnectbutton.Hide()

        if os.path.isfile(self.skyroofsettings):
            self.skyroofpresent = True
            try:
                with open(f'{self.skyroofsettings}', 'r', encoding = 'utf8') as file:
                    self.skyroofsettings = json.load(file)
                    self.skyroofgroups = self.skyroofsettings['Satellites']['SatelliteGroups']
                file.close()
                self.skyroofgrouplist = []
                for satgroup in self.skyroofgroups:
                    self.skyroofgrouplist.append(satgroup['Name'])
                wx.StaticText(self, -1, 'SkyRoof Groups: ', pos=(15,72))
                self.groupchoice = wx.Choice(self, choices=self.skyroofgrouplist, pos=(110,70), size=(140,25))
                self.skyroofbutton = wx.Button(self, label='← Load From SkyRoof', pos=(255,70), size=(125,25))
                self.skyroofbutton.Bind(wx.EVT_BUTTON, self.SkyRoof, self.skyroofbutton, id=self.skyroofbutton.GetId())

            except Exception as error:
                self.console.AppendText(f'\nError while processing SkyRoof Settings.json! - {error}\n')

        self.cmdlabel = wx.StaticText(self, -1, 'Commands: ', pos=(660,72))
        self.cmdchoice = wx.Choice(self, choices=self.cmdlist, pos=(735,70), size=(160,25))
        self.cmdbutton = wx.Button(self, label='Send', pos=(900,70), size=(80,25))
        self.cmdbutton.Bind(wx.EVT_BUTTON, self.serialCommand, self.cmdbutton, id=self.cmdbutton.GetId())
        self.cmdbutton.Disable()
        self.cmdchoice.Disable()

        self.satgridcounter = 0
        self.satgrid = wx.grid.Grid(self, size=(1000, 380), pos=(5,100))
        self.satgrid.CreateGrid(1,3)
        self.satgrid.EnableEditing(0)
        self.satgrid.EnableDragRowSize(0)
        self.satgrid.EnableDragGridSize(0)
        self.satgrid.SetSelectionMode(wx.grid.Grid.SelectRows)
        self.satgrid.SetColLabelValue(0, 'Satellite')
        self.satgrid.SetColSize(0, 140)
        self.satgrid.SetColLabelValue(1, 'TLE1')
        self.satgrid.SetColSize(1, 380)
        self.satgrid.SetColLabelValue(2, 'TLE2')
        self.satgrid.SetColSize(2, 380)
        self.satgrid.Bind(wx.grid.EVT_GRID_CELL_RIGHT_CLICK, self.gridContextMenu)
        self.satgrid.Bind(wx.EVT_KEY_DOWN, self.onKeyPress)
        self.satgrid.Bind(wx.grid.EVT_GRID_CELL_LEFT_DCLICK, self.onDclick)

        self.console = wx.TextCtrl(self, -1, '', pos=(5,480), size=(1000,220), style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.consolefont = wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_SEMIBOLD)
        self.console.SetFont(self.consolefont)

        gridattr = wx.grid.GridCellAttr()
        gridattr.SetFont(self.consolefont)
        self.satgrid.SetColAttr(0, gridattr)
        wx.StaticText(self, -1, 'Custom Command: ', pos=(5,705))
        self.cmdcustom = wx.TextCtrl(self, -1, '', pos=(115,702), size=(220,25), style=wx.TE_PROCESS_ENTER)
        self.cmdcustombutton = wx.Button(self, label='GO!', pos=(340,702), size=(80,25))
        self.Bind(wx.EVT_BUTTON, self.serialCommandCustom, self.cmdcustombutton, id=self.cmdcustombutton.GetId())
        self.Bind(wx.EVT_TEXT_ENTER, self.serialCommandCustom, id=self.cmdcustom.GetId())
        self.cmdcustom.Disable()
        self.cmdcustombutton.Disable()

        self.stopbutton = wx.Button(self, label='STOP!', pos=(430,702), size=(80,25))
        self.stopbutton.Bind(wx.EVT_BUTTON, self.doStop, self.stopbutton, id=self.stopbutton.GetId())
        self.stopbutton.Disable()

        self.debugbutton = wx.Button(self, label='Single Debug', pos=(520,702), size=(80,25))
        self.debugbutton.Bind(wx.EVT_BUTTON, self.onetimeDebug, self.debugbutton, id=self.debugbutton.GetId())
        self.debugbutton.Disable()

        self.uploadbutton = wx.Button(self, label='Upload TLE\'s', pos=(610,702), size=(80,25))
        self.uploadbutton.Bind(wx.EVT_BUTTON, self.uploadSats, self.uploadbutton, id=self.uploadbutton.GetId())
        self.uploadbutton.Disable()

        self.calbutton = wx.Button(self, label='Calibration Reference', pos=(740,702), size=(125,25))
        self.calbutton.Bind(wx.EVT_BUTTON, self.calCommandRef, self.calbutton, id=self.calbutton.GetId())

        self.refsbutton = wx.Button(self, label='Command Reference', pos=(880,702), size=(125,25))
        self.refsbutton.Bind(wx.EVT_BUTTON, self.getCommandRef, self.refsbutton, id=self.refsbutton.GetId())

        self.autoLoadFile()

    def onDclick(self, event):
        self.rowsel = event.GetRow()
        self.viewSatDetail(self)

    def viewSatDetail(self, event):
        satname = self.satgrid.GetCellValue(self.rowsel, 0)
        title = f'Detailed information for {satname}'
        self.console.AppendText(f'\nFetching data for {satname}...\n')
        self.noradid = self.satgrid.GetCellValue(self.rowsel, 1)[2:7]
        try:
            radioinfo = self.getRadioInfo()
            satinfo = self.getSatInfo()
        except IndexError as error:
            message = 'Could not find satellite in database!'
            self.showError(message, error)
            return
        tle = (self.satgrid.GetCellValue(self.rowsel, 1),self.satgrid.GetCellValue(self.rowsel, 2))
        satFrame(self, title, tle, satinfo, radioinfo, self.color)

    def onMouseOver(self, event):
        prev_rowcol = [None,None]
        def OnMouseMotion(event):
            x, y = event.GetPosition()
            row = self.satgrid.YToRow(y)
            col = self.satgrid.XToCol(x)
            try:
                if (row,col) != prev_rowcol and row >= 0 and col >= 0:
                    prev_rowcol[:] = [row,col]
                    noradid=self.selectedsats[int(row)]['tle1'][2:7]
                    satname=self.satgrid.GetCellValue(int(row), 0)
                    self.satgrid.GetGridWindow().SetToolTip(f'{satname} (NORAD: {noradid})')
            except IndexError as err:
                self.satgrid.GetGridWindow().SetToolTip(f'') #ignore empty row at end of wxgrid
                pass
        event.Skip()
        wx.EVT_MOTION(self.satgrid.GetGridWindow(), OnMouseMotion)
        #self.satgrid.Bind(wx.EVT_MOTION, OnMouseMotion)

    def serialConnect(self, event):
        try:
            self.port = self.comports[self.portchoice.GetStringSelection()]
            self.baud = int(self.speedchoice.GetStringSelection())
            self.console.AppendText(f'\nOpening {self.port}...\n')
            self.portchoice.Disable()
            self.speedchoice.Disable()
            self.connectbutton.Disable()
            if self.port == '':
                raise Exception('No port selected!')
            if self.baud == '':
                raise Exception('No baudrate selected!')
            self.serial = serial.Serial(self.port, self.baud, timeout=None)
            self.serial.flush()
            self.consolethread = Thread(target=self.serialThread, args=())
            self.consolethread.start()
            return
        except ValueError:
            message = 'Error!'
            error = 'Please select the correct COM port and baud rate.'
            self.showError(message, error)
            self.portchoice.Enable()
            self.speedchoice.Enable()
            self.connectbutton.Enable()
        except Exception as error:
            message = 'Error!'
            error = 'Please select the correct COM port and baud rate.'
            self.showError(message, error)
            self.console.AppendText(f'\nCan\'t open COM port!\n')
            self.portchoice.Enable()
            self.speedchoice.Enable()
            self.connectbutton.Enable()

    def serialDisconnect(self, event):
        try:
            if self.connected == True:
                self.console.AppendText(f'Closing {self.port}.\n')
                self.serial.write(b'\?SS\r')
                self.serial.write(b'\^0\r')
                time.sleep(2)
                self.connected = False
                self.serial.close()
                self.connectbutton.Show()
                self.debugbutton.Disable()
                self.uploadbutton.Disable()
                self.cmdchoice.Disable()
                self.cmdbutton.Disable()
                self.cmdcustom.Disable()
                self.cmdcustombutton.Disable()
                self.stopbutton.Disable()
                self.disconnectbutton.Hide()
                self.connectbutton.Show()
                self.portchoice.Enable()
                self.speedchoice.Enable()
                self.connectbutton.Enable()
        except:
                pass

    def uploadSats(self, event):
        try:
            filename = f'{self.apphome}\\kepfile.temp'
            if len(self.selectedsats) == 0:
                raise Exception('No sats selected!')
            if self.connected == False:
                raise Exception('Not connected to serial port!')
            if self.debugon == True:
                raise Exception('Debugging is enabled. Please disable it first.')
            f = open(filename, 'w')
            for sat in self.selectedsats:
                name = sat['amsat_name']
                line1 = sat['tle1']
                line2 = sat['tle2']
                f.write(f'{name}\r{line1}\r{line2}\r')
            f.close()
            with open(filename) as file:
                kepdata = file.read()
            self.kepbytes = kepdata.encode('ascii')
            file.close()
            os.remove(filename)
            self.writethread = Thread(target=self.uploadThread, args=())
            self.writethread.start()
            return
        except Exception as error:
            message = 'Error!'
            self.showError(message, error)

    def uploadThread(self):
        try:
            self.serial.write(b'\!\r')
            self.serial.write(b'\#\r')
            time.sleep(1)
            self.serial.write(self.kepbytes)
            time.sleep(3)
            self.serial.write(b'\r\r')
            if self.tracking == True:
                time.sleep(5)
                cmd = f'\${self.tracksatname}\r\^1\r'
                self.serial.write(cmd.encode('ascii'))
            return
        except Exception as error:
            message = 'Error!'
            self.showError(message, error)

    def serialThread(self):
        self.connected = True
        try:
            self.console.AppendText(f'\nWaiting 5s for controller to initialize...\n')
            time.sleep(5)
            self.console.AppendText(f'\nRequesting version...\n')
            self.serial.write(b'\n\?CV\r')
            self.connectbutton.Hide()
            self.debugbutton.Enable()
            self.uploadbutton.Enable()
            self.cmdchoice.Enable()
            self.cmdbutton.Enable()
            self.cmdcustom.Enable()
            self.cmdcustombutton.Enable()
            self.stopbutton.Enable()
            self.disconnectbutton.Show()
            while self.connected == True:
                time.sleep(0.00001)
                returntxt = self.serial.readline().decode('utf-8')
                self.console.AppendText(returntxt)
            return
        except Exception as error:
            message = 'Error!'
            self.showError(message, error)

    def serialCommand(self, event):
        try:
            if self.connected == False:
                raise Exception('Not connected to serial port!')
            self.serial.flush()
            cmdname = self.cmdchoice.GetStringSelection()
            if self.cmddict[cmdname] == '\D':
                if self.debugon == False:
                    self.debugon = True
                elif self.debugon == True:
                    self.debugon = False
            if self.cmddict[cmdname] == '\?SS':
                self.tracking = False
            cmd = f'{self.cmddict[cmdname]}\r'
            self.serial.write(cmd.encode('ascii'))
        except Exception as error:
            message = 'Error!'
            self.showError(message, error)

    def serialCommandCustom(self, event):
        try:
            if self.connected == False:
                raise Exception('Not connected to serial port!')
            self.serial.flush()
            cmd = self.cmdcustom.GetValue()
            if cmd == '\D' or '\d':
                if self.debugon == False:
                    self.debugon = True
                elif self.debugon == True:
                    self.debugon = False
            if cmd == '\?SS' or '\?ss':
                self.tracking = False
            self.serial.write(cmd.encode('ascii'))
            self.serial.write(b'\r')
            self.cmdcustom.Clear()
        except Exception as error:
            message = 'Error!'
            self.showError(message, error)

    def onetimeDebug(self, event):
        try:
            if self.connected == False:
                raise Exception('Not connected to serial port!')
            self.serial.flush()
            self.serial.write(b'\D\r\D\r')
        except Exception as error:
            message = 'Error!'
            self.showError(message, error)

    def doStop(self, event):
        try:
            if self.connected == False:
                raise Exception('Not connected to serial port!')
            self.serial.flush()
            self.serial.write(b'\?SS\r')
            self.console.AppendText('\nSent stop command.\n')
            self.tracking = False

        except Exception as error:
            message = 'Error!'
            self.showError(message, error)

    def updateTLEs(self, event):
        if self.satgridcounter == 0:
            self.console.AppendText(f'\nNo selected satellites! You can pick satellite(s) from the drop-down list above, and click \"Add to List\".\n\nOr you can load a previously saved list.\n')
            if self.skyroofpresent == True:
                self.console.AppendText(f'\nOr select a SkyRoof group and click \"Load From SkyRoof\".\n')
            return
        updatednum = 0
        for idx, sat in enumerate(self.selectedsats, start=0):
            noradid = sat['tle1'][2:7]
            for newsat in self.satlist:
                if int(noradid) == newsat['norad_cat_id']:
                    if sat['tle1'] != newsat['tle1'] or sat['tle2'] != newsat['tle2']:
                        sat.update({'tle1': newsat['tle1']})
                        sat.update({'tle2': newsat['tle2']})
                        self.satgrid.SetCellValue(idx, 1, sat['tle1'])
                        self.satgrid.SetCellValue(idx, 2, sat['tle2'])
                        self.satgrid.SetCellBackgroundColour(idx, 1, (25,220,25))
                        self.satgrid.SetCellBackgroundColour(idx, 2, (25,220,25))
                        updatednum += 1
                    else:
                        pass
                else:
                    pass
        if updatednum >0:
            self.console.AppendText(f'\nUpdated the TLE\'s for {updatednum} of the {self.satgridcounter} satellites in your list. Ready to upload to K3NG controller!\n')
        else:
            self.console.AppendText(f'\nFound no changes to TLE\'s for the current list. Ready to upload to K3NG controller!\n')
        if self.connected == False:
            self.console.AppendText(f'First select your serial port and baudrate, and click \"Connect\"! :)\n')

    def getSats(self, event):
        self.console.AppendText(f'\nDownloading satellite list and fresh TLE\'s from {self.amsaturl} and {self.tleurl}...\nPlease Wait...\n')
        self.satlist = [] # the list of each 'new' sat as a dict
        self.satnames = [] # list of sat names for the drop-down menu
        try:
            self.satchoice.Destroy()
            self.satlist = self.mergedSats()
            for sat in self.satlist:
                self.satnames.append(sat['amsat_name'])
            self.console.AppendText(f'\n{len(self.satlist)} satellites downloaded.\n')
            if len(self.selectedsats) == 0:
                self.console.AppendText(f'\nTo select satellites to upload to your controller, you can pick satellite(s) from the drop-down list above, and click \"Add to List\".\n\nOr you can load a previously saved list.\n')
                if self.skyroofpresent == True:
                    self.console.AppendText(f'\nOr select a SkyRoof group and click \"Load From SkyRoof\".\n')
            else:
                self.console.AppendText(f'\nTLE\'s may or may not be out of date for the {self.satgridcounter} satellites in your loaded list.\nBefore uploading to K3NG controller, click \"Update TLE List\".\nLines with updated data will be highlighted in green.\n')
            self.getbutton.Hide()
            self.updatebutton.Show()
            self.addbutton.Enable()
            self.satchoice = wx.Choice(self, choices=self.satnames, pos=(100,40), size=(140,30))
            self.Refresh()
        except Exception as error:
            self.satchoice = wx.Choice(self, choices=[], pos=(100,40), size=(140,25))
            self.console.AppendText(f'\nError making API request to SatNogs!\n')
            message = 'Error!'
            self.showError(message, error)
    
    def mergedSats(self):
        amsats = []
        satlist = []
        satnogs = []
        r = requests.get(self.tleurl)
        wx.Yield()
        satnogs = json.loads(r.content.decode())
        r = requests.get(self.amsaturl)
        wx.Yield()
        blocks = r.text.split('\n')
        for i in range(0, len(blocks), 3):
            chunk = blocks[i:i + 3]
            if len(chunk) == 1 and '' in chunk:
                break
            amsats.append(dict(amsat_name=chunk[0], tle1=chunk[1], tle2=chunk[2]))
        for nog in satnogs:
            nog.update({'amsat_name': False})
            for sat in amsats:
                if str(nog['norad_cat_id']).zfill(5) == sat['tle2'][2:7]:
                    nog['amsat_name'] = sat['amsat_name']
                    satlist.append(dict(nog))
            if nog['amsat_name'] == False:
                nog['amsat_name'] = nog['tle0']
                satlist.append(dict(nog))
        self.satlist = sorted(satlist, key=itemgetter('amsat_name'))
        return self.satlist

    def autoLoadFile(self):
        loadedlist = []
        loadedsats = []
        self.satgridcounter = 0
        self.selectedsats = []
        try:
            with open(self.satfile) as textdata:
                kepdata = textdata.read()
                textdata.close()
                blocks = kepdata.split('\n')
                for i in range(0, len(blocks), 3):
                    chunk = blocks[i:i + 3]
                    if len(chunk) == 1 or '' in chunk:
                        break
                    else:
                        loadedlist.append(dict(amsat_name=chunk[0], tle1=chunk[1], tle2=chunk[2]))
                        loadedsats = sorted(loadedlist, key=itemgetter('amsat_name'))
                for sat in loadedsats:
                    thissat = {'amsat_name': sat['amsat_name'], 'tle1': sat['tle1'], 'tle2': sat['tle2']}
                    self.fillGrid(self, thissat)
                    self.selectedsats.append(thissat)
            if self.satgridcounter == 0:
                self.console.AppendText(f'\nClick \"Fetch TLE\'s From Internet\" to download satellite TLE data. Then pick a satellite to add to your list.\n\nOr click \'Load a Saved List\'.\n')
                if self.skyroofpresent == True:
                    self.console.AppendText(f'\nOr select a SkyRoof group and click \"Load From SkyRoof\".\n')
            else:
                self.console.AppendText(f'\n{self.satgridcounter} satellites loaded from auto-save file: {self.satfile}.\n')
                self.console.AppendText(f'\nTLE\'s may or may not be out of date for the {self.satgridcounter} satellites in your auto-load list.\nClick \"Fetch TLE\'s From Internet\" to get fresh TLE\'s. Then, before uploading to K3NG controller, click \"Update TLE List\".\nLines with updated data will be highlighted in green.\n')
            self.Refresh()
            loadedlist.clear()
            loadedsats.clear()

        except FileNotFoundError as error:
            self.console.AppendText(f'\nNo auto-save file yet - Welcome :)\n')
            self.console.AppendText(f'\nClick \"Fetch TLE\'s From Internet\" to download satellite TLE data.\n')
            if self.skyroofpresent == True:
                self.console.AppendText(f'\nOr select a SkyRoof group and click \"Load From SkyRoof\".\n')
        except Exception as error:
            self.console.AppendText(f'\nProblem loading auto-save file. {error}\n')

    def SkyRoof(self, event):
        try:
            skyroofselectedgroup = self.groupchoice.GetStringSelection()
            if skyroofselectedgroup == '':
                self.console.AppendText(f'\nSelect SkyRoof group from the drop down list first!\n')
                return
            while len(self.selectedsats) > 0:
                for idx, sat in enumerate(self.selectedsats):
                    self.satgridcounter -= 1
                    self.selectedsats.pop(idx)
                    self.satgrid.DeleteRows(idx)
            self.satgridcounter = 0
            self.selectedsats = [] # empty the list - to be filled with sats from the file we're loading
            targetsats = []
            for satgroup in self.skyroofgroups:
                if satgroup['Name'] == skyroofselectedgroup:
                    for satid in satgroup['SatelliteIds']:
                        targetsats.append({'sat_id': satid})

            with open(f'{self.skyroofsatfile}', 'r', encoding = 'utf8') as file:
                satsjson = json.load(file)
            file.close()
            targetsatlookup = {d['sat_id']: d for d in targetsats}
            for sat in satsjson:
                if sat['sat_id'] in targetsatlookup:
                    self.selectedsats.append({'amsat_name': sat['name'], 'tle1': sat['Tle']['tle1'], 'tle2': sat['Tle']['tle2']})
                    self.fillGrid(self, {'amsat_name': sat['name'], 'tle1': sat['Tle']['tle1'], 'tle2': sat['Tle']['tle2']})
            self.console.AppendText(f'\n{self.satgridcounter} satellites loaded from SkyRoof Group: {self.groupchoice.GetStringSelection()}.\n')
            if self.satlist == []:
                self.console.AppendText(f'\nTLE\'s may or may not be out of date for the {self.satgridcounter} satellites in SkyRoof {self.groupchoice.GetStringSelection()}.\nClick \"Fetch TLE\'s From Internet\" to get fresh TLE\'s. Then, before uploading to K3NG controller, click \"Update TLE List\".\nLines with updated data will be highlighted in green.\n')
            else:
                self.console.AppendText(f'\nTLE\'s may or may not be out of date for the {self.satgridcounter} satellites in SkyRoof {self.groupchoice.GetStringSelection()}.\nClick \"Update TLE List\" before uploading to K3NG controller.\nLines with updated data will be highlighted in green.\n')
        except Exception as error:
            self.console.AppendText(f'Error while processing SkyRoof Settings.json! - {error}\n')

    def loadFile(self, event):
        if self.satgridcounter != 0:
            answer = wx.MessageBox('Warning! This will clear your current list. OK?', 'Confirm', wx.YES_NO | wx.CANCEL, self)
            if answer == wx.YES:
                pass
            if answer == wx.NO:
                return
            if answer == wx.CANCEL:
                return
        while len(self.selectedsats) > 0:
            for idx, sat in enumerate(self.selectedsats):
                self.satgridcounter -= 1
                self.selectedsats.pop(idx)
                self.satgrid.DeleteRows(idx)
        self.satgridcounter = 0
        self.selectedsats = [] # empty the list - to be filled with sats from the file we're loading
        try:
            textfile = wx.FileSelector('Choose an input file...', default_extension='*.tle', wildcard='TLE files (*.tle)|*.tle')
            with open(textfile) as text:
                loadedlist = []
                loadedsats = []
                kepdata = text.read()
                blocks = kepdata.split('\n')
                for i in range(0, len(blocks), 3):
                        chunk = blocks[i:i + 3]
                        if len(chunk) == 1 and '' in chunk:
                            break
                        loadedlist.append(dict(amsat_name=chunk[0], tle1=chunk[1], tle2=chunk[2]))
                        loadedsats = sorted(loadedlist, key=itemgetter('amsat_name'))
            self.satchoice.Destroy()
            for sat in loadedsats:
                thissat = {'amsat_name': sat['amsat_name'], 'tle1': sat['tle1'], 'tle2': sat['tle2']}
                self.fillGrid(self, thissat)
                self.selectedsats.append(thissat)
            self.console.AppendText(f'\nYou loaded {self.satgridcounter} satellites from {textfile}.\n')
            if self.satlist == []:
                self.console.AppendText(f'\nTLE\'s may or may not be out of date for the {self.satgridcounter} satellites in your loaded list.\nClick \"Fetch TLE\'s From Internet\" to get fresh TLE\'s. Then, before uploading to K3NG controller, click \"Update TLE List\".\nLines with updated data will be highlighted in green.\n')
            else:
                self.console.AppendText(f'\nTLE\'s may or may not be out of date for the {self.satgridcounter} satellites in your loaded list.\nClick \"Update TLE List\" before uploading to K3NG controller.\nLines with updated data will be highlighted in green.\n')
            self.satchoice = wx.Choice(self, choices=self.satnames, pos=(100,40), size=(140,30))
            loadedlist.clear()
            loadedsats.clear()
            self.Refresh()
        except FileNotFoundError as error:
            self.console.AppendText(f'Cancelled.\n')
        except Exception as error:
            message = 'Error!'
            self.showError(message, error)

    def saveFile(self, event):
        try:
            if len(self.selectedsats) == 0:
                raise Exception('No sats selected!')
            dlg = wx.FileDialog(self, 'Save to file:', '.', '', 'TLE files (*.tle|*.tle', wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
            if (dlg.ShowModal() == wx.ID_OK):
                self.filename = dlg.GetFilename()
                self.dirname = dlg.GetDirectory()
                f = open(os.path.join(self.dirname, self.filename), 'w')
                autosave = open(self.satfile, 'w')
                for sat in self.selectedsats:
                    name = sat['amsat_name']
                    line1 = sat['tle1']
                    line2 = sat['tle2']
                    f.write(f'{name}\r{line1}\r{line2}\r')
                    autosave.write(f'{name}\r{line1}\r{line2}\r')
                f.close()
                autosave.close()
                self.console.AppendText(f'\nSaved file {os.path.join(self.dirname, self.filename)}\n')
            dlg.Destroy()
        except Exception as error:
            message = 'Error!'
            self.showError(message, error)

    def clearSel(self, event):
        while len(self.selectedsats) > 0:
            for idx, sat in enumerate(self.selectedsats):
                self.satgridcounter -= 1
                self.selectedsats.pop(idx)
                self.satgrid.DeleteRows(idx)
        self.satnames.clear()
        self.satlist.clear()
        self.selectedsats.clear()
        self.satchoice.Destroy()
        self.satchoice = wx.Choice(self, choices=self.satnames, pos=(100,40), size=(140,30))
        self.Refresh()
        self.updatebutton.Hide()
        self.getbutton.Show()
        self.addbutton.Disable()
        self.console.AppendText(f'\nCleared current list as well as downloaded data. Starting over.\n')
        self.console.AppendText(f'\nClick \"Fetch TLE\'s From Internet\" to download satellite TLE data. Then pick a satellite to add to your list.\n\nOr click \'Load a Saved List\'.\n')
        if self.skyroofpresent == True:
            self.console.AppendText(f'\nOr select a SkyRoof group and click \"Load From SkyRoof\".\n')

    def fillGrid(self, event, data):
        self.satgrid.SetCellValue(self.satgridcounter,0,data['amsat_name'])
        self.satgrid.SetCellValue(self.satgridcounter,1,data['tle1'])
        self.satgrid.SetCellValue(self.satgridcounter,2,data['tle2'])
        self.satgrid.AppendRows(1)
        self.satgridcounter += 1
        self.console.AppendText(f"\nAdded {data['amsat_name']}.\n")

    def selectSat(self, event):
        try:
            if len(self.satnames) == 0:
                raise Exception('Download sats first!')
            # if self.satgridcounter >= 18:
            #     raise Exception('K3NG Rotator only holds 18 sats!')
            satname = self.satchoice.GetStringSelection()
            if len(self.selectedsats) >0:
                for sat in self.selectedsats:
                    if satname == sat['amsat_name']:
                        self.console.AppendText(f"\r{sat['amsat_name']} already in list!\n")
                        raise Exception('Already in list!')
                    else:
                        pass
            for sat in self.satlist:
                if sat['amsat_name'] == satname:
                    thissat = {'amsat_name': sat['amsat_name'], 'tle1': sat['tle1'], 'tle2': sat['tle2']}
                    self.fillGrid(self, thissat)
                    self.selectedsats.append(thissat)
        except Exception as error:
            message = 'Error!'
            self.showError(message, error)

    def trackSat(self, event):
        try:
            if self.connected == False:
                raise Exception('Not connected to controller!')
            self.tracksatname = self.satgrid.GetCellValue(self.rowsel, 0)
            self.noradid = self.satgrid.GetCellValue(self.rowsel, 1)[2:7]
            answer = wx.MessageBox('Upload the current list of satellite TLE\'s to the controller first?\n\n(Not always necessary if uploaded recently, but if lists are not in sync you will have problems!)', 'Confirm', wx.YES_NO | wx.CANCEL, self)
            if answer == wx.YES:
                self.tracking = True
                self.uploadSats(event)
            if answer == wx.NO:
                cmd = f'\${self.tracksatname}\r\^1\r'
                self.serial.write(cmd.encode('ascii'))
                self.tracking = True
            if answer == wx.CANCEL:
                return
            title = f'Detailed information for {self.tracksatname}'
            satinfo = self.getSatInfo()
            radioinfo = self.getRadioInfo()
            tle = (self.satgrid.GetCellValue(self.rowsel, 1),self.satgrid.GetCellValue(self.rowsel, 2))
            satFrame(self, title, tle, satinfo, radioinfo, self.color)
            return
        except Exception as error:
            message = 'Error!'
            self.showError(message, error)

    def stopTrack(self, event):
        try:
            if self.connected == False:
                raise Exception('Not connected to controller!')
            cmd = f'\^0\r'
            self.tracking = False
            self.serial.write(cmd.encode('ascii'))
            return
        except Exception as error:
            message = 'Error!'
            self.showError(message, error)

    def showError(self, message, error):
        self.error = error
        title = 'Error'
        frame = errorFrame(message, error, title, self.color)

    def gridContextMenu(self, event):
        self.gridmenu = wx.Menu()
        self.rowsel = event.GetRow()
        self.satgrid.SelectRow(self.rowsel)
        satrowname = self.satgrid.GetCellValue(self.rowsel, 0)
        self.menuview = wx.MenuItem(self.gridmenu, wx.ID_ANY, f'(ENT) View {satrowname} Details')
        self.menurem = wx.MenuItem(self.gridmenu, wx.ID_ANY, f'(DEL) Remove {satrowname} from list')
        self.menuprint = wx.MenuItem(self.gridmenu, wx.ID_ANY, '(P)rint selected rows to console')
        self.selectview = self.gridmenu.Append(self.menuview) 
        self.selectrem = self.gridmenu.Append(self.menurem)
        self.printlist = self.gridmenu.Append(self.menuprint)
        self.Bind(wx.EVT_MENU, self.viewSatDetail, self.selectview)
        self.Bind(wx.EVT_MENU, self.removeRow, self.selectrem)
        self.Bind(wx.EVT_MENU, self.printRows, self.menuprint)  
        if self.tracking == False and self.connected == True:
            self.menustarttrack = wx.MenuItem(self.gridmenu, wx.ID_ANY, f'Track {satrowname} on controller')
            self.tracksat = self.gridmenu.Append(self.menustarttrack)
            self.Bind(wx.EVT_MENU, self.trackSat, self.menustarttrack)                     
        if self.tracking == True and self.connected == True:
            self.menustoptrack = wx.MenuItem(self.gridmenu, wx.ID_ANY, f'Stop tracking {satrowname}')
            self.trackstop = self.gridmenu.Append(self.menustoptrack)
            self.Bind(wx.EVT_MENU, self.stopTrack, self.menustoptrack)
        self.PopupMenu(self.gridmenu)

    def sortVals(self,val):
        return val['gridrow']

    def onKeyPress(self, event):
        # print(event.GetKeyCode())
        if event.GetKeyCode() == 317: # cursor down key
            if event.ShiftDown():
                self.satgrid.MoveCursorDown(expandSelection=True)
            else:
                self.satgrid.MoveCursorDown(expandSelection=False)
            self.satgrid.MoveCursorLeftBlock(expandSelection=True)
            self.satgrid.MoveCursorRightBlock(expandSelection=True)
        if event.GetKeyCode() == 315: # cursor up key
            if event.ShiftDown():
                self.satgrid.MoveCursorUp(expandSelection=True)
            else:
                self.satgrid.MoveCursorUp(expandSelection=False)
            self.satgrid.MoveCursorLeftBlock(expandSelection=True)
            self.satgrid.MoveCursorRightBlock(expandSelection=True)
        if event.GetKeyCode() == 127: #delete
            self.removeRow(self)
        if event.GetKeyCode() == 80: #P
            self.printRows(self)
        if event.GetKeyCode() == 32: #space
            pass
        if event.GetKeyCode() == 13: #enter
            self.viewSatDetail(self)

    def removeRow(self, event):
        selectedrows = self.satgrid.GetSelectedRows() # list of row numbers that are selected in wxgrid
        deleteus = [] # create list of rows to delete
        for row in selectedrows:
            try:
                satname = self.satgrid.GetCellValue(row, 0) # get value of selected wxgrid row, from column 0
                if self.selectedsats[row]['amsat_name'] == satname: # find this row in the main dict and make sure it matches the item in wxgrid that we want to delete
                    deleteme = {'gridrow': row, 'sat': satname} # create dict for this row
                    deleteus.append(deleteme) # add this dict to the list of rows to delete
                    deleteus.sort(key=self.sortVals, reverse=True)
            except IndexError as err:
                self.satgrid.DeselectRow(row) #ignore empty row at end of wxgrid
                pass
        for deleteme in deleteus:
            self.satgrid.DeleteRows(deleteme['gridrow'], 1) # delete the row from the grid
            self.satgrid.DeselectRow(deleteme['gridrow']) # deselect the deleted row
            self.selectedsats.pop(deleteme['gridrow']) # pop this row from the list of row dicts
            self.satgridcounter -= 1 # deccrease my row counter down by 1
            self.console.AppendText(f"\nDeleting {deleteme['sat']}.\n") # prints each item that was selected
        self.satgrid.Refresh() # refresh the grid
        self.console.AppendText(f'\nDeleted {len(deleteus)} sats from list. {self.satgridcounter} remaining.\n')
        deleteus.clear() # finished with dict of rows to be deleted

    def printRows(self, event):
        selectedrows = self.satgrid.GetSelectedRows()
        self.console.AppendText(f'\r')
        for row in selectedrows:
            if int(row) >= len(self.selectedsats):
                self.satgrid.DeselectRow(row)
                return
            else:
                satname = self.satgrid.GetCellValue(row, 0)
                tle1 = self.satgrid.GetCellValue(row, 1)
                tle2 = self.satgrid.GetCellValue(row, 2)
                self.console.AppendText(f'{satname}\n')
                self.console.AppendText(f'{tle1}\n')
                self.console.AppendText(f'{tle2}\n')
        self.console.AppendText(f'\r')

    def getCommandRef(self, event):
        try:
            r = requests.get(self.cmdrefurl)
            self.console.AppendText(f'\r{r.text}\r\r')

        except Exception as error:
            message = 'Error!'
            self.showError(message, error)

    def calCommandRef(self, event):
        self.calhelp = """ ### Common Calibration Commands. See full Command Reference for more.
            \I              - display the current az starting point (usually 0 or 180)
            \J              - display the current az rotation capability (usually 360 or 450)

            \Ix[x][x]               - set az starting point (Eg: \I180)
            \Jx[x][x]               - set az rotation capability (Eg: \J360)

            \Ax[xxx][.][xxxx]           - manually calibrate azimuth
            \Ax[x][x]                   - manually calibrate azimuth (Rotary Encoder & Pulse Input features)
            \Bx[xxx][.][xxxx]           - manually calibrate elevation
            \Bx[x][x]                   - manually calibrate elevation (Rotary Encoder & Pulse Input features)

            \P                      - park antenna
            \PA[x][x][x]            - set / query park azimuth (Eg: \PA180)
            \PE[x][x][x]            - set / query park elevation (Eg \PE0)

            \?AZ                    - query azimuth
            \?AS                    - query azimuth rotation status
            \?EL                    - query elevation
            \?ES                    - query elevation rotation status
            \?AO                    - azimuth full CCW calibration      (Alpha Oscar, not A zero)
            \?AF                    - azimuth full CW calibration
            \?EO                    - elevation full DOWN calibration   (Echo Oscar, not E zero)
            \?EF                    - elevation full UP calibration

            \+                  - azimuth LCD display mode switch: normal, raw degrees, +overlap            
            \Q                  - Save settings in the EEPROM and restart
            \X0                 - clear calibration to defaults
            
        """
        self.console.AppendText(f'\n{self.calhelp}\n')

    def getSatTLE(self):
        id = int(self.noradid)
        r = requests.get(f"{self.tleurl}?norad_cat_id={id}")
        sat = json.loads(r.content.decode())
        return sat

    def getRadioInfo(self):
        radiolist = []
        id = int(self.noradid)
        r = requests.get(f"{self.radiourl}?satellite__norad_cat_id={id}")
        radios = json.loads(r.content.decode())
        for radio in radios:
            radiolist.append(radio)
        return radiolist

    def getSatInfo(self):
        id = int(self.noradid)
        r = requests.get(f"{self.saturl}?norad_cat_id={id}")
        satinfo = json.loads(r.content.decode())
        return dict(satinfo[0])

    def exit(self, event):
        self.console.AppendText(f'\r\nShutting down...\r\n')
        try:
            autosave = open(self.satfile, 'w')
            for sat in self.selectedsats:
                name = sat['amsat_name']
                line1 = sat['tle1']
                line2 = sat['tle2']
                autosave.write(f'{name}\r{line1}\r{line2}\r')
            autosave.close()
            self.console.AppendText(f'\nAuto-saved current list to {self.satfile}\r\n')
        except len(self.selectedsats) == 0:
            pass

        try:
            if self.connected == True:
                self.console.AppendText(f'Closing {self.port}.\n')
                self.serial.write(b'\?SS\r')
                self.serial.write(b'\^0\r')
                time.sleep(2)
                self.connected = False
                self.serial.close()
        except:
                pass

        self.Destroy()
        self.parent.Destroy()

class errorFrame(wx.Dialog):
    def __init__(self, message, error, title, color, parent=None):
        pos = wx.GetMousePosition()
        newpos = list(pos)
        newpos[0] -= 200
        newpos[1] -= 75
        pos=tuple(newpos)        
        wx.Dialog.__init__(self, parent=parent, title=title, pos=pos, style=wx.STAY_ON_TOP)
        self.color = color
        self.errorpage = wx.Panel(self)
        size=(340,200)
        self.SetSize(size)
        self.SetMinSize(size=size)
        self.SetMaxSize(size=size)
        self.SetBackgroundColour(self.color)
        self.messagetext = wx.StaticText(self.errorpage, -1, f'{message}', pos=(10, 10))
        self.messagetext.Wrap(300)
        self.errortext = wx.StaticText(self.errorpage, -1, f'{error}', pos=(10, 60))
        self.errortext.Wrap(300)
        self.okbutton = wx.Button(self.errorpage, label='OK', pos=(20, 140), size=(70, 40))
        self.okbutton.Bind(wx.EVT_BUTTON, self.okay)
        self.Show()

    def okay(self, event):
        self.Destroy()

class satFrame(wx.Frame):
    def __init__(self, event, title, tle, satinfo, radioinfo, color):
        pos = wx.GetMousePosition()
        newpos = list(pos)
        newpos[0] -= 450
        newpos[1] -= 10
        pos=tuple(newpos)
        wx.Frame.__init__(self, None, title=title, pos=pos)
        self.color = color
        self=self
        self.panel = wx.Panel(self)
        self.SetIcon(MainFrame.appIcon(self))
        self.SetMinSize((900,500))
        self.SetMaxSize((900,500))
        self.SetBackgroundColour(self.color)
        tz = timezone('UTC')
        now = datetime.now(tz)
        julian = Time(now)
        satellite = Satrec.twoline2rv(tle[0], tle[1])
        e, r, v = satellite.sgp4(julian.jd1,julian.jd2)
        if e != 0:
            pass
        r = CartesianRepresentation(r*u.km)
        v = CartesianDifferential(v*u.km/u.s)
        year = satellite.epochyr
        month, day, hour, minute, second = days2mdhms(satellite.epochyr, satellite.epochdays)
        epoch = datetime.strptime(f'{year} {month} {day} {hour} {minute} {second}', '%y %m %d %H %M %S.%f')
        formatedepoch = datetime.strftime(epoch, "%Y-%m-%d %H:%M:%S")
        teme = TEME(r.with_differentials(v), obstime=julian)
        itrs_geo = teme.transform_to(ITRS(obstime=julian))
        location = itrs_geo.earth_location
        lat = str(location.geodetic.lat.to_value())
        lon = str(location.geodetic.lon.to_value())
        alt = str(location.geodetic.height.to_value())
        alt = '{:.8}'.format(alt)
        lat = '{:.8}'.format(lat)
        lon = '{:.8}'.format(lon)

        satupdated = datetime.strftime(datetime.strptime(satinfo['updated'], '%Y-%m-%dT%H:%M:%S.%fZ'), '%Y-%m-%d %H:%M:%S')
        header = f"Name(s): {satinfo['name']} (aka {satinfo['names']}) --- Status: {satinfo['status']}\nSat ID: {satinfo['sat_id']} --- NORAD: {satinfo['norad_cat_id']}\nCurrent position: lat: {lat} / lon: {lon} / alt: {alt}\nOrbital data most accurate at: {formatedepoch} UTC --- Status of radios updated: {satupdated} UTC"
        font = wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_SEMIBOLD)
        textd = wx.StaticText(self, -1, header, pos=(5, 5))
        textd.SetFont(font)
        self.radgrid = wx.grid.Grid(self, size=(880, 370), pos=(5,90))
        self.radgrid.CreateGrid(1,7)
        self.radgrid.EnableEditing(0)
        self.radgrid.EnableDragRowSize(0)
        self.radgrid.EnableDragGridSize(0)
        self.radgrid.SetSelectionMode(wx.grid.Grid.SelectRows)
        self.radgrid.SetColLabelValue(0, 'Description')
        self.radgrid.SetColSize(0, 240)
        self.radgrid.SetColLabelValue(1, 'Uplink')
        self.radgrid.SetColSize(1, 100)
        self.radgrid.SetColLabelValue(2, 'Downlink')
        self.radgrid.SetColSize(2, 100)
        self.radgrid.SetColLabelValue(3, 'Mode')
        self.radgrid.SetColSize(3, 120)
        self.radgrid.SetColLabelValue(4, 'Invert')
        self.radgrid.SetColSize(4, 70)
        self.radgrid.SetColLabelValue(5, 'Status')
        self.radgrid.SetColSize(5, 70)
        self.radgrid.SetColLabelValue(6, 'Updated')
        self.radgrid.SetColSize(6, 80)
        self.Bind(wx.EVT_CLOSE, self.okay)
        self.panel.Fit()
        self.Layout()
        self.Fit()
        self.Show()

        for idx,radio in enumerate(radioinfo):
            try:
                upfreq = radio['uplink_low'] / 1000000
                upfreq = format(upfreq, '.3f')
            except:
                upfreq = radio['uplink_low']
            try:
                downfreq = radio['downlink_low'] / 1000000
                downfreq = format(downfreq, '.3f')
            except:
                downfreq = radio['downlink_low']
            self.radgrid.SetCellValue(idx,0,radio['description'])
            self.radgrid.SetCellValue(idx,1,f'{str(upfreq)} MHz')  
            self.radgrid.SetCellValue(idx,2,f'{str(downfreq)} MHz')
            self.radgrid.SetCellValue(idx,3,radio['mode'])
            self.radgrid.SetCellValue(idx,4,str(radio['invert']))
            self.radgrid.SetCellValue(idx,5,radio['status'])
            self.radgrid.SetCellValue(idx,6,datetime.strftime(datetime.strptime(radio['updated'], '%Y-%m-%dT%H:%M:%S.%fZ'), '%Y-%m-%d'))
            self.radgrid.AppendRows()
            self.radgridrows = idx

    def okay(self, event):
        self.Destroy()

class MainFrame(wx.Frame):
    def __init__(self):
        self.appName='K3NG Rotator Manager by VA3DXV'
        self.appVersion=0.5
        self.size=(1024,768)
        self.frameTitle = (f'{self.appName} version {self.appVersion}')
        wx.Frame.__init__(self, None, title=self.frameTitle, size=self.size)
        self.Bind(wx.EVT_CLOSE, self.exit)
        self.SetIcon(self.appIcon())
        self.SetMinSize(self.size)
        self.SetMaxSize(self.size)
        self.color = (255,255,255)
        self.SetBackgroundColour(self.color)
        self.panel = MainPanel(self, self.color, self.size)
        self.Show()

    def exit(self, event):
        self.panel.console.AppendText(f'\nPlease use the \"Exit\" button to gracefully close the application.\n')
        return

    def appIcon(self):
        iconcode = PyEmbeddedImage(
            b'iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAABHNCSVQICAgIfAhkiAAAELdJ'
            b'REFUeJztm3l0lPW5xz/vO+8smUkmkIUJSRiSBkhYyqYQNnvrpSDaIlrAKqKcesXac+9V2a5V'
            b'6j3Wa6+AQr3agrYVoahVoUUgFIGyCJElFBATliFiSGYSspDMZCazz7y/+0eAkn2BNj2nfM/J'
            b'H3nf3/PL8/3+tud53l8kSdbwzwy5px3oadwSoKcd6GncEqCnHehp3BKgpx3oadwSoKcd+AeH'
            b'0MPFd+E3ApaK/v1XiIMHi4QQqgiFQuIfAR6PRxQVFQmn09nk+e9+d1T07v2ztTDP0B7DduJg'
            b'oUDtMsj/MZwlI8PMpk3fZ9y4HEBCo7l5IXQ4HKKiopzq6noghMGgIEkyIHVoe9WPS5cuoaoq'
            b'JpMJSZIYMSKN1FTDqPz8KqPPZ9kDZ0Sr9m13/cRDsHc5nJISE218/PEcxo0b3h1+HUDwyitv'
            b'8MIL+fz850Xs2XOSrVtPcvDgRUIhO0ajQq9evWhLDFmWMRqNBINBKioqCAaD9O7d+4oI6Tid'
            b'htz8fE8x7C9szb4NAcRwyH8PTsUZjT5+//sZTJ48+WYxboHDh0/g8Ujk5BiJi1Ow2wW7dh3i'
            b'gw/2smVLLWfOfIXVqiclpU+r9pIk4fP5cLvd1NbWoqoqCQkJAEya1E8qLCyeZLOd3wm11Z1w'
            b'p8QAe/4Mrwn4T/Hss5v/7uva7/cKm+20WLv2UzFjxuvCYJgu4uL+Xbz44k4RDre+94RCIWGz'
            b'2cRnn30mDhw4IOx2+7V3xcWXRN++L+2G2brmbFuZASsfg51PwWXuvtvE6tVz0Gr1XRrRrkNQ'
            b'XV2F01mHx+PGbI4jObkvo0YNYObM4Ywdm8jJky4+/PAUpaUlTJ06AJ3O2JSIRkMwGCQQCBAK'
            b'hXC73cTHx2MwGEhIiMVsFpnbtlWVwuGTTeyaOZIOR9dBUXx6ejHr1z9DWlrfvzF5+Pzzc9x5'
            b'5zv88pcFvPXWEd5/30ZBwVekpuqwWpMYMCCHOXNGEgx+yVtvHaG42Mfdd2ej0zXd4CVJoqqq'
            b'inA4jKqq1NXVYbFY0Gg0DB9ulWy2khGnT/s3QomnDQEeXwyb7gUPS5YMZNas7/3NyQNEIhIO'
            b'R5ScnH4MGuQmGBTkba9k7bpj2M45GDIkhbS0ZKZOnYTLdYa1a4twOmWmTBmEovyVgk6nw2w2'
            b'c+nSJSRJIhqNEgqFSEpKQqOR6dfP1Csvr9bj9ebvb8UNkQqf2mGhsFqfFnZ7ZbfWr7PO1S27'
            b'6xEO+8Wxwovi4adfF/Cc6Nt3sdi7d9eVte4T99//vICF4re/zW9hGwqFREFBgdi3b5/Yv3+/'
            b'2Ldvn6irqxNCCBGNRsRjj60uhTuuTevrIsHSh6EwHTQ8/vhtpKdbujyS3miI6T/8gC2bT3bc'
            b'uAVUAgE3kYgPRTFw+7D+vPf60+zYcT+qquEHP3iTL744hlYbw6uvzicl5WtWrNhEXV1dk160'
            b'Wi0mkwkhGo99IQR2u72RrKzh8cf/xWq1jny4mQAiBmp/AA6sVsEDD4zsBgE4/JmN/C0OHn9i'
            b'Jzt3FnXaTgiV555bxbhxr/Ltb6/mpz/9hHPnGo/tadPGsHnz/UAWDz74ATU1dWRlZfDCC/dy'
            b'/ryL9euPtujvahzQSFqmrq4Ol8sFwKhRmQwcmDUbFsRcJwC3w/GREGXSpGFkZw/ulgA7tjcq'
            b'ffmyj1mz/kheXmdngiA2NgFZTsPlMrB8+eeMv+NtVqzbhaqqjB+fy4oVM7HZfKxZ8xEAs2ff'
            b'R0qKn40bLxCJBJr0Fhsb27R3ISgrKwPAYIjhO9+xjoZjo/8qgMZxH3ytATMzZw4AlC6TFyJE'
            b'cXExoCUz04TfH2bOnO1s23aiQ1tJ0rB06WOcOPEkhYVPsufgo2TlZvPsD/ezdu0+AB54YDQj'
            b'RlhZvfoALlclycnx3HnneE6cqOTs2Zom/Wk0GrRa7bVlIMsyTqfz2iyYPHmI0rfv8PuuCCAM'
            b'9MufgGQiLU3PmDHWLpMHaGgQfPFFAEhixYq7ef75cfj9fh5+eDtbt3YsQuMe4EGSFL417pts'
            b'/O199Btt5tVlR6itvYzRaOTRR0dTVWXm4EEHIDNtmoVgsJxz5+xNejIajcTFxV0TAEBVVZxO'
            b'JwBDhvTjm98cNB6m6WUgjYv6oYhKJk7Uk5ra9c0PwO324nIJjMZyBg3S89JL97Bs2e00NPh4'
            b'5JHtbNvW9nIoL/fwox+tZd68t3njjT8RCgXJTOnHK8/kcv6Ch127bABMmJCBRmPm2LGvARg2'
            b'bBRGYyJ1dTUt+ryePDTGCLW1tQCYTEZGjEgYCpo0BWrGgicOVG6/PY5wOEp3Er36ehfhcAid'
            b'TsFgkACJRYtmoNHILFhwhLlz89iwQWXatBwiEfU6x+Dllz/k17/+CjDw8cefk53dm7vuGs/Q'
            b'CVmQqKPc3kgwJSUerTYWlysEQN++RsxmPUJ0nDUChEIhAoEABoOB4cP7xZtMmWMUCA6GIhQl'
            b'SGbmaHS6Gwt7NRoNiqK98pvMM89MR1UFixcXMGdOHuPH78Zi0ROJNLbQaiUOHaoHYmjM+CTq'
            b'6tyNfckSRH3U118GIDbWjKJoESIKgKqKK+Q7FkCSJAKBAPX19RgMBoYOTZaMxpjBCsgDIRaL'
            b'RcvgwSbC4TB6fddF6NWrN1qtjlDITTDov+6NzMKF9yJJEosWFbB3b4RVq4Yxc+YYolFBKBRk'
            b'3rytOJ3VeDwyEycm8q1vjQAgq08CrywZwj3Tx17pK4DFUorF0h8AISAYdBCNdi5NlySJyspK'
            b'LBYLZnMCWq1moALFA+EcOt1wFEVpsXY6C3OykcQhGux/kbDbZQY3OUllFiz4HkIInn32GC++'
            b'+CWDBlmZMmUwTzyxkVGjYpkyJYaKigivvz4Hk8kMgNFk4ifPP3atl8TEBPbufY7k5BQAkpL6'
            b'sGbNXYwePRKv14vJZOq0v4mJ8aSkJA+S4WwSeDEajaSnp2MwtFtBahOxWoUJWQlEoxa+/NLe'
            b'SgsNCxdOZ/nyMTQ0eJk7N4977lmDovj4xS8ewmCIxWo1XSPfGiRJxmrNICam0UeDwcCDDz7E'
            b'oEGDOk3+aoAUH69jxAglSYb0WEhDiBq6OfjXCI4alQro2LbNA0RbbbNw4b2sWDEWrzfI7t2J'
            b'TJ06Ap3OQCQSIRq9IQea4CrR5s+upssgCATUOBkicRAhJiYdna5FvaBLmD59MAaD4IsvZM6d'
            b'K2+jlcyCBdNZvHAkmL9i/n/8mV27T9Enqe2R7ypCoRB+v7+FCJIk4fV6r72LRIiTwQ3Y0etj'
            b'0GpvTIDsbCuzZmXidufwq18VAGobLWV+9tIMVv3PCFyheh6ae4J1O4rRG25OodXv9+Pz+dqc'
            b'Bdc/lyHkAS1utxuv19PCoGuQ+fGT/VGsB1i7toTTp9uaBaBRZBY8NZ2VS8fhrL7IkW1OvA03'
            b'ZwnIstwq+ebQKXhkyG4AA0KIThl1hHHjBzDrjlR8vm/z3E+qaWhwttNaw8JF97Jy1SgURbB6'
            b'dWmncoeOcPny5Q5PMxUJn0H2yJBwGXREoxFqa2sJBALtGnYEWdby6iujsWbUsu3Pxbzw0zIg'
            b'3J4FCxY0ng719T7mzv3TDYvg9XrbfS9JEpcqXRwt8F2WIe48DMPjcVFWZu92HHA90vulsuq1'
            b'bxAXP5I1a1y8tmIzoUBDOxaNp8Nrr43B5/Mzd+52tmzpngjhcJhAINDqbFZVFbPZjMlkIuAN'
            b'oXG6bDIoxeCkqipCSUn0Wph5o5g5cwBr3wwiGyz8ZLmd/3p1M25ve8tBZsGCe1m+fAwej59H'
            b'H93O1q1dryxFo9E2BQBQFAVZlqmursEbiBbLYDkHViKRKsrLC2loaG+kOo/Nm8+SmdmbD99X'
            b'idXcyf/9d3/umvIhmzYdIBwOtmHVGDavXJmL1xtg3ry8drPI1hCJRIhcTTSaQZKkKwmRlwMH'
            b'HMLlCp+TQVMAqR6I4cgR53WBwo3hzV/KzHjQgDW1DwUHTUycEOXI4W8we/YJpk5dxwcfHKK8'
            b'vJZQqPnJ0xg2L18+ivr6MI88ktfpypKqqpw/f77dNnq9TCAQpKystl5VvzqmAA5IL4LU8WfO'
            b'RCgvL8NiubFvAcGgG3eDRLnk4Dvfj7D0qf7s+DSR379fycv/m83+/R+zf38JiYmnyM5uoE+f'
            b'1CYJmN/vp6zMgSRpqK8PM2vWJ7z3XoRZs26jrS/6qqpis9lwu91tTn9VjfDJJyrz5gXYvftc'
            b'ERgdCkhBOH8IlPHl5UGKimrIzKwlJSW12wLYbFqKTmVAKEKtycfCRckUFtr4t2e0HDkaw/a8'
            b'O9i40cvRo3UcOuQC6gBx5edqeqtc+cDZi6lT0+jbtzdCNNYPWkMgEKCmpmVh5CoUBez2GN58'
            b'MwdVPUQgEDoMG0NXin/xn0D0aZ+vVNmxQ09ubn+SkvqgKF2vDQLU1bkIBo1APDQ0FijfXdeP'
            b'9cffYdNLucyfP57584MUF+dQVlZPUVEthw6FgVpAxmJRyc1NJCcnm5wcc7sJEvy19B2JRNr8'
            b'bK/RqJw/35uamliWLYsPBwIVW+Ba9bPPcfjXExAYe/JkPQ7HZTIzfcTFdS8+37UrDDSzVVTU'
            b'sikcOljN9O8FURQ9AwemM3BgOpMnw9NPd+tPAVBTU0NFRUU75CUuX1Z5990kGmuPF47DgRNw'
            b'bUFJfrhtIwzk4kUvu3cXUllZ3q2YIBoNkJ9vpkWVJhIH9Wl8erQav8/X5X7bwtXRby+K1WoF'
            b'Z88GcTj6gMEBnN0EDj80qX9r3odeT4Gz3x/+oPDd71aQlTUISepagiJJEe64YzcZGdaWTslR'
            b'ki1BFO3NS3urqqpwu93IcuuboyQJ3G6VDRtyGx/0Ol5Gpe39q++vE0C6BI53oOBFux0++qiE'
            b'jIw0BgzI6aQrYU6fdlJSEmTSpDFIUivhrwBBKnv2eLH0CTBmbALQvQKMEIILFy5QXl7eJnkh'
            b'wGyW2bLFSGFhAuCDypp3YGPl1TbNdrm038DEH8Kh/hs2/IUJE+JIS+tHTExH1RaV1zYcZ9ni'
            b'HGqrW7/F0RwxKSeYP/s0K1fd2a3NtqysjNLS0nZtNRpBebmJTZsGXHmyvwTe+831bZpZSxVQ'
            b'9jJcejsYDMsffXSJCRO+Jisr57pKb0tUV9dxdFsCWRkRkhPOd7x3yAJhEuzdG8RuLyczs3/7'
            b'7ZvB7XbjcDjavaglhMBojGHFit6UlfUCSlT49GU4eKkJ41ZM9XBqK+ycCg3Mm9efJUtyyc7O'
            b'blOExgsJQSQpitfr7dzmKWSQIDY2sUuVqPr6eoqKigiFQm1OfQCtNkJeXizLl+eiqiHg7U/h'
            b'rRlwpkmY28r8kYIgFoO6C9alrF9fyG23GUlPT8Vs7t3qbqvVaoFGcXS6+E6T6Qqi0SglJSVU'
            b'VFSgqmq75PV6wdmzWn79dhaqLICdlahfLWlOHtq8JfazanjjEjEV9xNpkI4f/5phw/SkpSWj'
            b'18fcLE6dRiQSoaioiMrKxr2rvSNPr1O5eNHE0qWjqaw1Q+LnKvo/Pon/V3taa9/OGfdyId94'
            b'JhZXZKK3wc/hw+fJzc2gTx8DkqSg0fx9btk6HA5sNhsNDQ0dlrr0OsHFapnFL2XgKE6AuFMQ'
            b'fnclrrdWtWXT/iFfu34/IikNnKPq68vZt8/J0KF6kpK0aLUxN/W2aHOEQiFKS0u5cOEC0Wi0'
            b'w3KdQSdxsUpiyapEyo8NAC5C8JN3CH69CM60WeSQbv3X2D85bgnQ0w70NG4J0NMO9DRuCdDT'
            b'DvQ0bgnQ0w70NP4fBHygMgeHMXsAAAAASUVORK5CYII=')
        icon = iconcode.GetIcon()
        return icon

if __name__ == '__main__':
    app = wx.App(redirect=False)
    frame = MainFrame()
    app.MainLoop()
