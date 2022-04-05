#!/usr/local/bin/python3.9
#pyinstaller --onefile --windowed --icon=icon.ico -F k3ngmanager.py
from distutils.command.upload import upload
import wx
import wx.grid
from operator import itemgetter
import os
import time
import requests
import serial
import serial.tools.list_ports
from wx.lib.embeddedimage import PyEmbeddedImage
import threading

class Kepler(wx.Panel):
    def __init__(self, parent, color, size):
        wx.Panel.__init__(self, parent=parent)
        self.parent=parent
        self.color=color
        self.SetSize(size)
        self.SetMinSize(size=(size))
        self.SetMaxSize(size=(size))
        self.saturl = 'https://www.amsat.org/tle/current/nasabare.txt'
        self.cmdrefurl = 'https://raw.githubusercontent.com/wiki/k3ng/k3ng_rotator_controller/820-Command-Reference.md'
        self.satnames = []
        self.selectedsats = []
        self.satlist = []
        self.comports = {}
        self.portslist = []
        self.speedslist = ['1200','2400','4800','9600','14400','19200','38400','57600','115200']
        for comport in serial.tools.list_ports.comports():
            self.comports[comport.description] = comport.device
            self.portslist.append(comport.description)

        self.cmddict = {'Enable/Disable Debug': '\D', 'Query Clock': '\?CL', 'GPS Sync Status': '\?GS', 'Query AZ/EL Position': 'C2', 'Read Loaded Sats': '\@', 'Erase Loaded Sats': '\!', 'Re-calc Sats': '\&', 'Ping Remote': '\PG', 'Query AZ Start': '\I', 'Query AZ Capability': '\J', 'Stop All Rotation': '\?SS', }
        self.cmdlist = list(self.cmddict.keys())
        self.connected = False
        self.debugon = False

        self.getbutton = wx.Button(self, label='Download TLE', pos=(20,5), size=(160,25))
        self.Bind(wx.EVT_BUTTON, self.GetSats, self.getbutton, id=self.getbutton.GetId())

        self.updatebutton = wx.Button(self, label='Update These TLEs', pos=(20,5), size=(160,25))
        self.Bind(wx.EVT_BUTTON, self.UpdateKeps, self.updatebutton, id=self.updatebutton.GetId())
        self.updatebutton.Hide()

        self.loadbutton = wx.Button(self, label='Load Saved List', pos=(210,5), size=(110,25))
        self.Bind(wx.EVT_BUTTON, self.LoadFile, self.loadbutton, id=self.loadbutton.GetId())

        self.clearbutton = wx.Button(self, label='Clear', pos=(800,5), size=(80,25))
        self.Bind(wx.EVT_BUTTON, self.clearSel, self.clearbutton, id=self.clearbutton.GetId())

        self.exitbutton = wx.Button(self, label='Exit', pos=(900,5), size=(80,25))
        self.Bind(wx.EVT_BUTTON, self.exit, self.exitbutton, id=self.exitbutton.GetId())

        wx.StaticText(self, -1, 'Satellite: ', pos=(20,42))
        self.satchoice = wx.Choice(self, choices=self.satnames, pos=(75,40), size=(140,25))

        self.addbutton = wx.Button(self, label='Add to List', pos=(230,40), size=(110,25))
        self.Bind(wx.EVT_BUTTON, self.AddSat, self.addbutton, id=self.addbutton.GetId())

        self.exportbutton = wx.Button(self, label='Save List', pos=(350,40), size=(110,25))
        self.Bind(wx.EVT_BUTTON, self.ExportSats, self.exportbutton, id=self.exportbutton.GetId())

        self.cmdlabel = wx.StaticText(self, -1, 'Commands: ', pos=(640,70))
        self.cmdchoice = wx.Choice(self, choices=self.cmdlist, pos=(710,70))
        self.cmdbutton = wx.Button(self, label='Send', pos=(900,70), size=(80,25))
        self.Bind(wx.EVT_BUTTON, self.serialCommand, self.cmdbutton, id=self.cmdbutton.GetId())
        self.cmdbutton.Disable()
        self.cmdchoice.Disable()

        wx.StaticText(self, -1, 'COM Port: ', pos=(480,42))
        self.portchoice = wx.Choice(self, choices=self.portslist, pos=(540,40), size=(230,25))

        wx.StaticText(self, -1, 'Baudrate: ', pos=(775,42))
        self.speedchoice = wx.Choice(self, choices=self.speedslist, pos=(830,40))

        self.connectbutton = wx.Button(self, label='Connect', pos=(900,40), size=(80,25))
        self.Bind(wx.EVT_BUTTON, self.serialConnect, self.connectbutton, id=self.connectbutton.GetId())

        self.debugbutton = wx.Button(self, label='Single Debug', pos=(900,40), size=(80,25))
        self.Bind(wx.EVT_BUTTON, self.onetimeDebug, self.debugbutton, id=self.debugbutton.GetId())
        self.debugbutton.Hide()

        self.uploadbutton = wx.Button(self, label='Upload to Controller', pos=(20,70), size=(120,25))
        self.Bind(wx.EVT_BUTTON, self.UploadSats, self.uploadbutton, id=self.uploadbutton.GetId())
        self.uploadbutton.Disable()

        self.satgridrow = 0
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
        self.satgrid.Bind(wx.grid.EVT_GRID_CELL_RIGHT_CLICK, self.gridpopMenu)

        self.console = wx.TextCtrl(self, -1, '', pos=(5,480), size=(1000,220), style=wx.TE_MULTILINE | wx.TE_READONLY)

        wx.StaticText(self, -1, 'Custom Command: ', pos=(5,705))
        self.cmdcustom = wx.TextCtrl(self, -1, '', pos=(115,702), size=(220,22), style=wx.TE_PROCESS_ENTER)
        self.cmdcustombutton = wx.Button(self, label='Send', pos=(350,702), size=(80,22))
        self.Bind(wx.EVT_BUTTON, self.serialCommandCustom, self.cmdcustombutton, id=self.cmdcustombutton.GetId())
        self.Bind(wx.EVT_TEXT_ENTER, self.serialCommandCustom, id=self.cmdcustom.GetId())
        self.cmdcustom.Disable()
        self.cmdcustombutton.Disable()

        self.stopbutton = wx.Button(self, label='STOP!', pos=(460,702), size=(80,22))
        self.Bind(wx.EVT_BUTTON, self.stopcmd, self.stopbutton, id=self.stopbutton.GetId())
        self.stopbutton.Disable()

        self.refsbutton = wx.Button(self, label='Command Reference', pos=(580,702), size=(125,22))
        self.Bind(wx.EVT_BUTTON, self.getcmdref, self.refsbutton, id=self.refsbutton.GetId())

    def serialConnect(self, event):
        try:
            self.port = self.comports[self.portchoice.GetStringSelection()]
            self.baud = int(self.speedchoice.GetStringSelection())
            self.console.AppendText(f'Opening {self.port}...\n')
            self.portchoice.Disable()
            self.speedchoice.Disable()
            self.connectbutton.Disable()
            if self.port == '':
                raise Exception('No port selected!')
            if self.baud == '':
                raise Exception('No baudrate selected!')
            self.serial = serial.Serial(self.port, self.baud, timeout=None)
            self.serial.flush()
            self.consolethread = threading.Thread(target=self.serialThread, args=())
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
            self.showError(message, error)
            self.console.AppendText(f'Can\'t open COM port!\n')
            self.portchoice.Enable()
            self.speedchoice.Enable()
            self.connectbutton.Enable()

    def UploadSats(self, event):
        try:
            filename = 'kepfile.temp'
            if len(self.selectedsats) == 0:
                raise Exception('No sats selected!')
            if self.connected == False:
                raise Exception('Not connected to serial port!')
            if self.debugon == True:
                raise Exception('Debugging is enabled. Please disable it first.')
            f = open(filename, 'w')
            for sat in self.selectedsats:
                name = sat['Name']
                line1 = sat[1]
                line2 = sat[2]
                f.write(f'{name}\r{line1}\r{line2}\r')
            f.close()
            with open(filename) as file:
                kepdata = file.read()
            self.kepbytes = kepdata.encode('ascii')
            file.close()
            os.remove(filename)
            self.writethread = threading.Thread(target=self.uploadThread, args=())
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
            return

        except Exception as error:
            message = 'Error!'
            self.showError(message, error)

    def serialThread(self):
        self.connected = True
        try:
            self.console.AppendText(f'Waiting 5s for controller to initialize...\n')
            time.sleep(5)
            self.console.AppendText(f'Requesting version...\n')
            self.serial.write(b'\n\?CV\r')
            self.connectbutton.Hide()
            self.debugbutton.Show()
            self.uploadbutton.Enable()
            self.cmdchoice.Enable()
            self.cmdbutton.Enable()
            self.cmdcustom.Enable()
            self.cmdcustombutton.Enable()
            self.stopbutton.Enable()
            while self.connected == True:
                time.sleep(0.1)
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

    def stopcmd(self, event):
        try:
            if self.connected == False:
                raise Exception('Not connected to serial port!')
            self.serial.flush()
            self.serial.write(b'\?SS\r')

        except Exception as error:
            message = 'Error!'
            self.showError(message, error)

    def UpdateKeps(self, event):
        self.console.AppendText(f'Updating with kepler data from {self.saturl}...\n')
        updatednum = 0
        netlist = []
        r = requests.get(self.saturl)
        blocks = r.text.split('\n')
        for i in range(0, len(blocks), 3):
                chunk = blocks[i:i + 3]
                if len(chunk) == 1 and '' in chunk:
                    break
                netlist.append(dict(Name=chunk[0], One=chunk[1], Two=chunk[2]))
                self.netsats = sorted(netlist, key=itemgetter('Name'))
        for idx, sat in enumerate(self.selectedsats, start=0):
            for netsat in self.netsats:
                if netsat['Name'] == sat['Name']:
                    if sat[1] != netsat['One'] or sat[2] != netsat['Two']:
                        sat.update({1: netsat['One']})
                        sat.update({2: netsat['Two']})
                        self.satgrid.SetCellValue(idx, 1, sat[1])
                        self.satgrid.SetCellValue(idx, 2, sat[2])
                        self.satgrid.SetCellBackgroundColour(idx, 1, (25,220,25))
                        self.satgrid.SetCellBackgroundColour(idx, 2, (25,220,25))
                        updatednum += 1
                    else:
                        pass
                else:
                    pass
        netlist.clear()
        if updatednum >0:
            self.console.AppendText(f'Updated the kepler data for {updatednum} satellites. Please save this file if you wish to keep it.\n')
        else:
            self.console.AppendText(f'Found no changes to kepler data for the current list.\n')            

    def GetSats(self, event):
        self.console.AppendText(f'Downloading satellite list and kepler data from {self.saturl}...\n')
        getlist = []
        self.satlist = []
        self.satnames = []
        try:
            r = requests.get(self.saturl)
            while len(self.selectedsats) > 0:            
                for idx, sat in enumerate(self.selectedsats):
                    self.satgridrow -= 1
                    self.selectedsats.pop(idx)
                    self.satgrid.DeleteRows(idx)
            self.satgridrow = 0
            self.selectedsats = []
            blocks = r.text.split('\n')
            for i in range(0, len(blocks), 3):
                    chunk = blocks[i:i + 3]
                    if len(chunk) == 1 and '' in chunk:
                        break
                    getlist.append(dict(Name=chunk[0], One=chunk[1], Two=chunk[2]))
                    self.satlist = sorted(getlist, key=itemgetter('Name'))
            numsats = len(self.satlist)
            self.console.AppendText(f'{numsats} Satellites downloaded.\n')
            self.satchoice.Destroy()
            for sat in self.satlist:
                self.satnames.append(sat['Name'])
            self.satchoice = wx.Choice(self, choices=self.satnames, pos=(75,40), size=(140,30))
            getlist.clear()
            self.Refresh()
        except Exception as error:
            message = 'Error!'
            self.showError(message, error)

    def ExportSats(self, event):
        try:
            if len(self.selectedsats) == 0:
                raise Exception('No sats selected!')
            dlg = wx.FileDialog(self, 'Save to file:', '.', '', 'Text (*.txt)|*.txt', wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
            if (dlg.ShowModal() == wx.ID_OK):
                self.filename = dlg.GetFilename()
                self.dirname = dlg.GetDirectory()
                f = open(os.path.join(self.dirname, self.filename), 'w')
                for sat in self.selectedsats:
                    name = sat['Name']
                    line1 = sat[1]
                    line2 = sat[2]
                    f.write(f'{name}\r{line1}\r{line2}\r')
                f.close()
                self.console.AppendText(f'Saved file {os.path.join(self.dirname, self.filename)}\r\n')
            dlg.Destroy()
        except Exception as error:
            message = 'Error!'
            self.showError(message, error)

    def LoadFile(self, event):
        list = []
        self.satlist = []
        self.loadedsats = []
        self.satnames = []
        self.getsats = []
        while len(self.selectedsats) > 0:            
            for idx, sat in enumerate(self.selectedsats):
                self.satgridrow -= 1
                self.selectedsats.pop(idx)
                self.satgrid.DeleteRows(idx)
        self.satgridrow = 0
        self.selectedsats = []
        try:
            textfile = wx.FileSelector('Choose an input file...', default_extension='*.txt', wildcard='TXT files (*.txt)|*.txt')
            with open(textfile) as text:
                kepdata = text.read()
                blocks = kepdata.split('\n')
                for i in range(0, len(blocks), 3):
                        chunk = blocks[i:i + 3]
                        if len(chunk) == 1 and '' in chunk:
                            break
                        list.append(dict(Name=chunk[0], One=chunk[1], Two=chunk[2]))
                        self.loadedsats = sorted(list, key=itemgetter('Name'))
            numsats = len(self.loadedsats)
            self.satchoice.Destroy()
            for sat in self.loadedsats:
                thissat = {'Name': sat['Name'], 1: sat['One'], 2: sat['Two']}
                self.satgrid.SetCellValue(self.satgridrow,0,thissat['Name'])
                self.satgrid.SetCellValue(self.satgridrow,1,thissat[1])
                self.satgrid.SetCellValue(self.satgridrow,2,thissat[2])
                self.satgrid.AppendRows(1)
                self.satgridrow += 1
                self.selectedsats.append(thissat)
            self.console.AppendText(f'You loaded {self.satgridrow} satellites from {textfile}.\nKepler data may be out of date. Use the \"Update These Keps\" button before uploading to controller.\n')
            r = requests.get(self.saturl)
            blocks = r.text.split('\n')
            for i in range(0, len(blocks), 3):
                    chunk = blocks[i:i + 3]
                    if len(chunk) == 1 and '' in chunk:
                        break
                    self.getsats.append(dict(Name=chunk[0], One=chunk[1], Two=chunk[2]))
                    self.satlist = sorted(self.getsats, key=itemgetter('Name'))
            for sat in self.satlist:
                self.satnames.append(sat['Name'])
            self.satchoice = wx.Choice(self, choices=self.satnames, pos=(75,40), size=(140,30))
            self.getbutton.Hide()
            self.updatebutton.Show()
            list.clear()
            self.Refresh()
        except Exception as error:
            message = 'Error!'
            self.showError(message, error)

    def clearSel(self, event):
        while len(self.selectedsats) > 0:
            for idx, sat in enumerate(self.selectedsats):
                self.satgridrow -= 1
                self.selectedsats.pop(idx)
                self.satgrid.DeleteRows(idx)
        self.satnames = []
        self.satlist = []
        self.selectedsats = []
        self.satchoice.Destroy()
        self.satchoice = wx.Choice(self, choices=self.satnames, pos=(75,40), size=(140,30))
        self.Refresh()
        self.updatebutton.Hide()
        self.getbutton.Show()

    def AddSat(self, event):
        try:
            if len(self.satnames) == 0:
                raise Exception('Load sats first!')
            if self.satgridrow >= 18:
                raise Exception('K3NG Rotator only holds 18 sats!')
            satname = self.satchoice.GetStringSelection()
            if len(self.selectedsats) >0:
                for sat in self.selectedsats:
                    if satname == sat['Name']:
                        raise Exception(f'{sat["Name"]} is already in list!')
                    else:
                        pass
            for sat in self.satlist:
                if sat['Name'] == satname:
                    thissat = {'Name': sat['Name'], 1: sat['One'], 2: sat['Two']}
                    self.satgrid.SetCellValue(self.satgridrow,0,satname)
                    self.satgrid.SetCellValue(self.satgridrow,1,thissat[1])
                    self.satgrid.SetCellValue(self.satgridrow,2,thissat[2])
                    self.satgrid.AppendRows(1)
                    self.satgridrow += 1
                    self.selectedsats.append(thissat)
        except Exception as error:
            message = 'Error!'
            self.showError(message, error)

    def trackSat(self, event):
        try:
            if self.connected == False:
                raise Exception('Not connected to controller!')
            tracksatname = self.satgrid.GetCellValue(self.rowsel, 0)
            cmd = f'\${tracksatname}\r\^1\r'
            self.serial.write(cmd.encode('ascii'))
            return

        except Exception as error:
            message = 'Error!'
            self.showError(message, error)
 
    def stopTrack(self, event):
        try:
            if self.connected == False:
                raise Exception('Not connected to controller!')
            cmd = f'\^0\r'
            self.serial.write(cmd.encode('ascii'))
            return

        except Exception as error:
            message = 'Error!'
            self.showError(message, error)
    
    def showError(self, message, error):
        self.error = error
        title = 'Error'
        frame = errorFrame(message, error, title, self.color)

    def gridpopMenu(self, event):
        self.gridmenu = wx.Menu()
        self.rowsel = event.GetRow()

        self.menurem = wx.MenuItem(self.gridmenu, wx.ID_ANY, 'Remove from list')
        self.menuprint = wx.MenuItem(self.gridmenu, wx.ID_ANY, 'Print list to console')
        self.menustarttrack = wx.MenuItem(self.gridmenu, wx.ID_ANY, 'Track this Satellite')
        self.menustoptrack = wx.MenuItem(self.gridmenu, wx.ID_ANY, 'Stop Sat Tracking')

        self.selectrem = self.gridmenu.Append(self.menurem)
        self.printlist = self.gridmenu.Append(self.menuprint)
        self.tracksat = self.gridmenu.Append(self.menustarttrack)
        self.trackstop = self.gridmenu.Append(self.menustoptrack)

        self.Bind(wx.EVT_MENU, self.removerow, self.selectrem)
        self.Bind(wx.EVT_MENU, self.printrows, self.menuprint)
        self.Bind(wx.EVT_MENU, self.trackSat, self.menustarttrack) 
        self.Bind(wx.EVT_MENU, self.stopTrack, self.menustoptrack) 
        self.PopupMenu(self.gridmenu)

    def removerow(self, event):
        satname = self.satgrid.GetCellValue(self.rowsel, 0)
        for idx, sat in enumerate(self.selectedsats):
            if sat['Name'] == satname:
                self.selectedsats.pop(idx)
                self.satgrid.DeleteRows(self.rowsel)
                self.satgridrow -= 1

    def printrows(self, event):
        self.console.AppendText(f'\r')
        for idx, sat in enumerate(self.selectedsats):
            self.console.AppendText(f'\n{sat["Name"]}')
            self.console.AppendText(f'\n{sat[1]}')
            self.console.AppendText(f'\n{sat[2]}')
        self.console.AppendText(f'\r')

    def getcmdref(self, event):
        try:
            r = requests.get(self.cmdrefurl)
            self.console.AppendText(f'\r{r.text}\r\r')

        except Exception as error:
            message = 'Error!'
            self.showError(message, error)

    def exit(self, event):
        if self.connected == False:
            self.parent.Destroy()
        else:
            self.serial.write(b'\?SS\r')
            self.serial.write(b'\^0\r')
            time.sleep(2)
            self.connected = False
            self.console.AppendText(f'Closing {self.port}.\n')
            self.serial.close()
            self.parent.Destroy()
        
class errorFrame(wx.Dialog):
    def __init__(self, message, error, title, color, parent=None):
        wx.Dialog.__init__(self, parent=parent, title=title, style=wx.STAY_ON_TOP)
        self.color = color
        self.errorpage = wx.Panel(self)
        size=(340,240)
        self.SetSize(size)
        self.SetMinSize(size=size)
        self.SetMaxSize(size=size)
        self.SetBackgroundColour(self.color)
        self.messagetext = wx.StaticText(self.errorpage, -1, f'{message}', pos=(10, 10))
        self.messagetext.Wrap(300)
        self.errortext = wx.StaticText(self.errorpage, -1, f'{error}', pos=(10, 60))
        self.errortext.Wrap(300)
        self.okbutton = wx.Button(self.errorpage, label='OK', pos=(120, 180), size=(70, 40))
        self.Bind(wx.EVT_BUTTON, self.okay)
        self.Show()

    def okay(self, event):
        self.Destroy()

class MainFrame(wx.Frame):
    def __init__(self):
        self.appName='K3NG Rotator Manager by VA3DXV'
        self.appVersion=0.3
        size=(1024,768)
        frameTitle = (f'{self.appName} version {self.appVersion}')
        wx.Frame.__init__(self, None, title=frameTitle, size=size)
        self.SetIcon(self.appIcon())
        self.SetMinSize(size)
        self.SetMaxSize(size)
        self.color = (255,255,255)
        self.SetBackgroundColour(self.color)
        self.panel = Kepler(self, self.color, size)
        self.Bind(wx.EVT_CLOSE, self.exit)
        self.Show()

    def exit(self, event):
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
