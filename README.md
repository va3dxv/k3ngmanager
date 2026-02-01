# k3ngmanager
k3ngmanager is a simple to use GUI tool to manage and diagnose the operation of an Arduino based K3NG rotator controller (link: https://github.com/k3ng/k3ng_rotator_controller).

Helps get your Arduino based K3NG antenna rotator updated, finely tuned, and dialed in!

A must-have tool for setting up a portable or stand-alone satellite antenna tracker.

Connects to your rotator controller via serial port, or USB-serial, for easy configuration and debugging.

- Upload TLE orbital data to your controller for self-contained antenna-to-satellite tracking
- Select a satellite and start/stop rotator tracking
- Display complete orbital and radio details from a chosen satellite
- Debugging log for rotator controller troubleshooting
- A full terminal-like status console
- One click command reference and calibration reference

Makes it very easy to upload TLE tracking data to the controller, for those who use it standalone or portable with an LCD or Nextion screen.
Satellite TLE data can be pulled from a variety of sources...

- From your saved groups in your installation of SkyRoof (by VE3NEA - link: https://github.com/VE3NEA/SkyRoof)
- From the internet (SatNogs+AmSat)
- From a list you've previously saved
- Auto-loads the last list you worked with (in %appdata%\Roaming\k3ngmanager)

Python 3.11 / wxPython 4.2.0 msw (phoenix) wxWidgets 3.2.0

Tested on Windows, MacOS Ventura and Debian Bookworm
Self contained Windows .exe package no installation required. 

![k3ngmanager](https://raw.githubusercontent.com/va3dxv/k3ngmanager/main/k3ngmanager1.jpg)

![k3ngmanager](https://raw.githubusercontent.com/va3dxv/k3ngmanager/main/k3ngmanager2.jpg)
