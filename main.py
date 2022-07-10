# This Python file uses the following encoding: utf-8
import os
from pathlib import Path
import sys
import platform
from datetime import datetime, date, time, timedelta
import time

from PySide2.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QToolButton, QProgressBar, QFrame, QMenu, QMessageBox, QAction, QMessageBox
from PySide2.QtCore import QFile, QTimer, QThread, QRunnable, QThreadPool
from PySide2.QtUiTools import QUiLoader

import requests
import json

isWindows = (platform.system() == "Windows")

def ReadConfigFile():
    with open("config.txt") as file:
        return file.read()

def ReadAPIKey(configText):
    # Find line API_KEY in config contents
    lines = configText.split('\n')
    for line in configText.split('\n'):
        if "API_KEY" in line:
            return line.split('=')[1]

def ReadDeviceIpAddress(configText):
    # Find line IP_ADDRESS in config contents
    lines = configText.split('\n')
    for line in configText.split('\n'):
        if "IP_ADDRESS" in line:
            return line.split('=')[1]

def ReadDevicePortNumber(configText):
    # Find line API_KEY in config contents
    lines = configText.split('\n')
    final = 80
    for line in configText.split('\n'):
        if "PORT" in line:
            final = line.split('=')[1]
    return final

def TemperatureToString(temperature_c, fahrenheit):
    decimal_places = 2
    if fahrenheit:
        return str(round(temperature_c * 9 / 5 + 32, decimal_places)) + " °F"
    else:
        return str(round(temperature_c, decimal_places)) + " °C"

def getSeparationChar():
    if isWindows:
        return '#'
    else:
        return '-'

# configContents = None
# ApiKey = None
# DeviceIpAddress = None
configContents = ReadConfigFile()
ApiKey = ReadAPIKey(configContents)
DeviceIpAddress = ReadDeviceIpAddress(configContents)
DevicePortNumber = ReadDevicePortNumber(configContents)

OctoprintBaseUrl = "http://" + DeviceIpAddress + ":" + DevicePortNumber + "/"
OctoprintCameraUrl = OctoprintBaseUrl + "webcam/?action=snapshot"
OctoprintRequestUrl = OctoprintBaseUrl + "api/"
OctoprintRequestUrl_Job = OctoprintRequestUrl + "job"
OctoprintRequestUrl_Server = OctoprintRequestUrl + "server"
OctoprintRequestUrl_Printer = OctoprintRequestUrl + "printer"
OctoprintRequestUrl_Version = OctoprintRequestUrl + "version"
OctoprintRequestUrl_Settings = OctoprintRequestUrl + "settings"
OctoprintRequestUrl_Connection = OctoprintRequestUrl + "connection"
OctoprintRequestUrl_Printer_State = OctoprintRequestUrl_Printer + "/state"
OctoprintRequestUrl_Tool = OctoprintRequestUrl + "printer/tool"
OctoprintRequestUrl_Bed = OctoprintRequestUrl + "printer/bed"

class Widget(QWidget):
    lastOperationReportedError = False
    DefaultTimeoutIntervalAfterError = 3  # Seconds
    Request_DefaultTimeoutPeriod = 1  # Seconds
    session = requests.Session()

    actionText_disableHeaters = "Turn heaters off"

    def __init__(self):
        super(Widget, self).__init__()
        self.session.headers.update({'X-Api-Key': ApiKey, 'content-type': 'application/json'})

        self.load_ui()
        self.timeLabel = self.findChild(QLabel, 'timeLabel')
        self.dateLabel = self.findChild(QLabel, 'dateLabel')
        self.label_connectedStatus = self.findChild(QLabel, 'label_connectedStatus')
        self.label_printerConnectionStatus = self.findChild(QLabel, 'label_printerConnectionStatus')
        self.label_jobStatus = self.findChild(QLabel, 'label_jobStatus')
        self.printStatus_progressBar = self.findChild(QProgressBar, 'printStatus_progressBar')
        self.label_printerTemps = self.findChild(QLabel, 'label_printerTemps')
        self.jobStatusFrame = self.findChild(QFrame, 'jobStatusFrame')
        self.label_job_timeRemaining = self.findChild(QLabel, 'label_job_timeRemaining')
        self.label_job_timeElapsed = self.findChild(QLabel, 'label_job_timeElapsed')
        self.label_jobName = self.findChild(QLabel, 'label_jobName')

        self.menu = self.findChild(QToolButton, 'toolButton_menu')
        # self.menu.
        self.menuItems = QMenu()
        self.populateMenu()

        self.s_RefreshData()
        # Update time and date now
        self.printTimeAndDate()
        # print(self.GetServerVersion())
        # Start timer for refreshing time and date
        self.timer_refreshTimeAndDate = QTimer()
        self.timer_refreshTimeAndDate.timeout.connect(self.printTimeAndDate)
        self.timer_refreshTimeAndDate.start(1000)
        # Start timer for refreshing data
        self.timer_refreshData = QTimer()
        self.timer_refreshData.timeout.connect(self.RefreshData)
        self.timer_refreshData.start(1000)

    def RefreshAll(self):
        self.RefreshData()
        self.populateMenu()

    def populateMenu(self):
        self.menuItems = QMenu()
        # Create refresh action
        self.action_refresh = QAction("Refresh", self)
        self.action_refresh.triggered.connect(self.RefreshAll)
        self.menuItems.addAction(self.action_refresh)
        # Add submenu
        try:
            submenu = QMenu("Preheat")
            # List profiles
            profiles = self.Command_GetDefaultTemperatures()
            submenu.addAction(self.actionText_disableHeaters)
            submenu.addSeparator()
            for profile in profiles["profiles"]:
                submenu.addAction(profile)
        except:
            submenu = QMenu("Preheat")
            action_unavailable = QAction("Profiles not available", self)
            action_unavailable.setEnabled(False)
            submenu.addAction(action_unavailable)

        self.menuItems.addMenu(submenu)
        # Add listener to detect which item was selected
        submenu.triggered.connect(self.preheat_menuItemSelected)
        self.menu.setMenu(self.menuItems)

    def preheat_menuItemSelected(self, action):
        # Get the selected profile
        profile = action.text()
        if(profile != self.actionText_disableHeaters):
            # Set the temps
            self.Command_SetTempsFromProfile(profile)
        else:
            reply = QMessageBox.question(self, 'Disable heaters', "Are you sure you want to turn off the heaters?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                # Turn off heaters
                self.Command_SetBedTemp(0)
                self.Command_SetToolTemp(0)

    def load_ui(self):
        loader = QUiLoader()
        path = os.fspath(Path(__file__).resolve().parent / "form.ui")
        ui_file = QFile(path)
        ui_file.open(QFile.ReadOnly)
        loader.load(ui_file, self)
        ui_file.close()

    def printTimeAndDate(self):
        # d = datetime.now()
        separation_char = ""
        if isWindows:
            separation_char = '#'
        else:
            separation_char = '-'

        timeText = datetime.now().strftime("%{0}I:%M %p".format(separation_char))
        dateText = datetime.now().strftime("%A, %B %{0}d, %Y".format(separation_char))
        self.timeLabel.setText(timeText)
        self.dateLabel.setText(dateText)

    def s_RefreshData(self):
        # if(self.lastOperationReportedError):
        #     # self.timer_refreshData.setInterval(self.DefaultTimeoutIntervalAfterError)
        #     self.timer_refreshData.stop()
        #     self.timer_refreshData.start(self.DefaultTimeoutIntervalAfterError)
        #     self.lastOperationReportedError = False
        #     return False
        # else:
        #     self.timer_refreshData.setInterval(1000)
        #     self.RefreshData()
        try:
            self.RefreshData()
        except:
            print("Connection error")
            self.SetToDisconnectedView()

    def RefreshData(self):
        response = self.session.get(OctoprintRequestUrl_Job, timeout=self.Request_DefaultTimeoutPeriod)
        if response.status_code != 200:
            print('HTTP', response.status_code)
            self.SetToDisconnectedView()
        else:
            self.label_connectedStatus.setText("Connected")

            response_connection = self.session.get(OctoprintRequestUrl_Connection, timeout=self.Request_DefaultTimeoutPeriod)
            self.label_printerConnectionStatus.setText(response_connection.json()["current"]["state"])

            data = response.json()
            state = data["state"]
            if state == "Printing":
                # self.label_jobStatus.setText("Printing")
                progress = int(data["progress"]["completion"]) * 100
                self.printStatus_progressBar.setValue(progress)

                secondsRemaining = data["progress"]["printTimeLeft"]
                secondsElapsed = data["progress"]["printTime"]

                futureTime = datetime.now() + timedelta(seconds=secondsRemaining)

                finishTimeAndDate = futureTime.strftime("%m/%d/%Y at %{0}I:%M %p".format(getSeparationChar()))
                elapsedTime = time.strftime('%H:%M:%S', time.gmtime(secondsElapsed))
                remainingTime = time.strftime('%H:%M:%S', time.gmtime(secondsRemaining))

                self.label_job_timeElapsed.setText(elapsedTime)
                self.label_job_timeRemaining.setText("{0} (on {1})".format(remainingTime, finishTimeAndDate))
                self.label_jobName.setText(data["job"]["file"]["name"])
                self.jobStatusFrame.setVisible(True)
            else:
                self.jobStatusFrame.setVisible(False)

            self.label_jobStatus.setText(state)

            info_tool_response = self.session.get(OctoprintRequestUrl_Tool, timeout=self.Request_DefaultTimeoutPeriod)
            info_bed_response = self.session.get(OctoprintRequestUrl_Bed, timeout=self.Request_DefaultTimeoutPeriod)
            tool_temp = TemperatureToString(info_tool_response.json()["tool0"]["actual"], False)
            bed_temp = TemperatureToString(info_bed_response.json()["bed"]["actual"], False)

            # Check if tool has a target temperature
            if info_tool_response.json()["tool0"]["target"] != None or info_tool_response.json()["tool0"]["target"] != 0:
                tool_target = "(Target: {0})".format(TemperatureToString(info_tool_response.json()["tool0"]["target"], False))
            else:
                tool_target = ""

            # Check if bed has a target temperature
            if info_bed_response.json()["bed"]["target"] != None or info_bed_response.json()["bed"]["target"] != 0:
                bed_target = "(Target: {0})".format(TemperatureToString(info_bed_response.json()["bed"]["target"], False))
            else:
                bed_target = ""

            self.label_printerTemps.setText("Tool: {0} {1} \nBed: {2} {3}".format(tool_temp, tool_target, bed_temp, bed_target))
        
    
    def SetToDisconnectedView(self):
        self.label_jobStatus.setText("")
        self.label_printerTemps.setText("")
        self.label_connectedStatus.setText("Not connected")
        self.jobStatusFrame.setVisible(False)
        self.lastOperationReportedError = True

    def GetServerVersion(self):
        # Get Octoprint server version
        response = self.session.get(OctoprintRequestUrl_Version, timeout=self.Request_DefaultTimeoutPeriod)
        if response.status_code != 200:
            return "Error"
        else:
            return response.json()["server"]

    def Command_SetToolTemp(self, tool_temp_c):
        request = {'command': 'target', 'targets': {'tool0': tool_temp_c}}
        response = self.session.post(OctoprintRequestUrl_Tool, json=request, timeout=self.Request_DefaultTimeoutPeriod)
        print(response)
        return response

    def Command_SetBedTemp(self, bed_temp_c):
        request = {'command': 'target', 'target': bed_temp_c}
        response = self.session.post(OctoprintRequestUrl_Bed, json=request, timeout=self.Request_DefaultTimeoutPeriod)
        print(response)
        return response

    # Get default profiles & temperatures
    def Command_GetDefaultTemperatures(self):
        response = self.session.get(OctoprintRequestUrl_Settings, timeout=self.Request_DefaultTimeoutPeriod)
        profiles = {}
        print(response.json())
        profileList = response.json()["temperature"]["profiles"]
        for profile in profileList:
            profiles.update({profile["name"]: {"tool": profile["extruder"], "bed": profile["bed"]}})

        root = {"profiles": profiles}
        return root

    def Command_SetTempsFromProfile(self, profileName):
        profiles = self.Command_GetDefaultTemperatures()
        if profileName in profiles["profiles"]:
            tool_temp = profiles["profiles"][profileName]["tool"]
            bed_temp = profiles["profiles"][profileName]["bed"]
            # Ask user for confirmation
            reply = QMessageBox.question(self, 'Preheat', "Set preheat profile to \"" + profileName + "\". \nTool: "+TemperatureToString(tool_temp, 0) + "\nBed: "+TemperatureToString(bed_temp, 0)+"\n\nAre you sure you want to apply the profile now?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.Command_SetToolTemp(tool_temp)
                self.Command_SetBedTemp(bed_temp)
            return True
        else:
            return False

if __name__ == "__main__":
    app = QApplication([])
    widget = Widget()
    widget.show()
    sys.exit(app.exec_())
