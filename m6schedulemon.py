#!/usr/bin/env python

from mark6control import Mark6, Mark6Exception, Mark6Scan
from Tkinter import *
import tkMessageBox
import ttk
import subprocess 
import argparse
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from time import sleep


class GUI(Frame):
    '''
    classdocs
    '''  
    def __init__(self, parent, args, mark6):
        '''
        Constructor
        '''
        Frame.__init__(self, parent)
        self.parent=parent
	self.args = args
	self.mark6 = mark6
	self.showFutureScans = BooleanVar()
	self.showFutureScans.set(False)

        self.initialize_user_interface()
	self.insert_data()

    def onChkShowFutureClick(self, event):
	self.insert_data()

    def initialize_user_interface(self):
        """	
	setup the widgets
        """

        self.parent.title("Mark6 monitor: %s" % (self.args.recorder))       
        self.parent.grid_rowconfigure(0,weight=1)
        self.parent.grid_columnconfigure(0,weight=100)
        self.parent.grid_columnconfigure(1,weight=1)
        self.parent.grid_rowconfigure(10,weight=100)
        self.parent.grid_columnconfigure(10,weight=1)
        self.parent.grid_rowconfigure(20,weight=1)
        self.parent.grid_columnconfigure(20,weight=1)
        #self.parent.config(background="lavender")


        # Define widgets in the options frame
	optionsFrame = LabelFrame(self.parent, text='Options')
	optionsFrame.grid(row=20,column=0, columnspan=2, sticky='new')

	chkShowFuture = Checkbutton(optionsFrame, text = "show future scans", variable =  self.showFutureScans)
	chkShowFuture.grid(row=0,column=0, columnspan=2,sticky='ew')
	chkShowFuture.bind("<ButtonRelease-1>", self.onChkShowFutureClick)

	# main frame
	mainFrame = LabelFrame(self.parent, text='')
	mainFrame.grid(row=0,column=0, columnspan=2, sticky='new')
	
	Label(mainFrame, text="Schedule: %s" % self.args.schedule, font=("Courier", 12)).grid(row=0,column=0)


        # treeview frame

        self.tree = ttk.Treeview( self.parent, columns=('source', 'start', 'stop', 'duration','gaptime', 'status'))
        self.tree.heading('#0', text='scan')
        self.tree.heading('#1', text='source')
        self.tree.heading('#2', text='start')
        self.tree.heading('#3', text='stop')
        self.tree.heading('#4', text='duration [s]')
        self.tree.heading('#5', text='gap [s]')
        self.tree.heading('#6', text='status', anchor=W)
        self.tree.column('#0', width=160,stretch=NO)
        self.tree.column('#1', width=130, stretch=NO)
        self.tree.column('#2', width=130, stretch=NO)
        self.tree.column('#3', width=130, stretch=NO)
        self.tree.column('#4', width=70, stretch=NO)
        self.tree.column('#5', width=70, stretch=NO)
        self.tree.column('#6', stretch=YES)
        self.tree.grid(row=10, column=0, sticky='nesw')

	vsb = ttk.Scrollbar(orient="vertical",command=self.tree.yview)
    	self.tree.configure(yscrollcommand=vsb.set)
	vsb.grid(row=10, column=1, sticky='ns')

    def insert_data(self):
        """
        Insertion method.
        """
	self.tree.tag_configure('missing', background='red')
	self.tree.tag_configure('pending', background='yellow')
	self.tree.tag_configure('OK', background='white')
	self.tree.tag_configure('recording', background='green')

	
	scans, refresh = getScanList(self.args, self.mark6)
	# clear the treeview
	self.tree.delete(*self.tree.get_children())

	# calculate the gap times
	for i in range(len(scans)-1):
		scans[i]["gapTime"] = (scans[i+1]['startDateTime'] - scans[i]['stopDateTime']).seconds

	scans[-1]['gapTime'] = ""

	dtNow = datetime.utcnow()

	for scan in scans:
		if scan["status"] == "recording":
			status = "recording...." 
		else:
			status = scan["status"]

		if scan["startDateTime"] > dtNow:
			if status != "pending" and self.showFutureScans.get() == False:
				break
		
        	self.tree.insert('', 0, text=scan["name"], values=(scan["source"], scan["startTimeStr"], scan["stopTimeStr"], scan["duration"], scan["gapTime"], status), tags=(scan["status"]))

	if refresh == -1:
		return
	elif refresh == 0:
		self.parent.after(10000, self.insert_data)
	else:
		self.parent.after(refresh*1000, self.insert_data)


def getRecordedScans(mark6):
	mark6.readScans()

	return mark6.scans

def getRecordedScanSize(scanname, files):

	for file in files:
		size, name = file.split()
		if os.path.splitext(name)[0] == scanname:
			return int(size)
	return -1

def displayScanList(scans):

	for scan in scans:
		print scan['name'], scan['status']

	



def getScanList(args, mark6):

	tree = ET.parse(args.schedule)
	root = tree.getroot()

	scans = []
	sleepSec = -1

	recScans = mark6.readScanList()

	for scan in root.findall("scan"):
		scanInfo = {}
		duration = int(scan.get('duration'))
		scanName = scan.get('scan_name')
		station = scan.get('station_code')
        	exp = scan.get('experiment')
		startTime = scan.get('start_time')

		dtStart = datetime.strptime(startTime, '%Y%j%H%M%S')
       		dtStop = dtStart + timedelta(seconds=duration)
        	dtNow = datetime.utcnow()

		recFilename = "%s_%s_%s" %(exp,station,scanName)


		recScan = mark6.getScanByName(recFilename)
		if recScan:
			recSize = recScan.size
			scanInfo['status'] = "OK"
		else:
			recSize = 0
			scanInfo['status'] = "missing"
		
		scanInfo['name'] = scanName
		scanInfo['duration'] = duration
		scanInfo['startTimeStr'] = dtStart.strftime('%Y-%j %H:%M:%S')
		scanInfo['stopTimeStr'] = dtStop.strftime('%Y-%j %H:%M:%S')
		scanInfo['startDateTime'] = dtStart
		scanInfo['stopDateTime'] = dtStop
		scanInfo['recsize'] = recSize
		scanInfo['source'] = scan.get('source')


		#lastRecSize = recSize

		if dtStop < dtNow:	# past scan
			scans.append(scanInfo)
		elif dtStart < dtNow and dtStop > dtNow: 	# scan currently running
			state = mark6.getRecordingState()
			if state == "recording":
				scanInfo['status'] = "recording"
			else:
				# scan should be recording but is not
				tkMessageBox.showerror("Error", "scan %s is not recording on recorder %s" % (scanName, args.recorder))

			scans.append(scanInfo)
			return scans, 0
		elif dtStart > dtNow:				# future scan
			if sleepSec == -1:	# first future scan
				scanInfo['status'] = "pending"
				sleep = dtStart - datetime.utcnow() + timedelta(seconds=10)
				print "sleeping until: ", datetime.utcnow() + sleep
				sleepSec = sleep.seconds
			else:
				scanInfo['status'] = ""
			
			scans.append(scanInfo)



	return scans, sleepSec

def main():

	parser = argparse.ArgumentParser(description='Monitor the recordering progress of a Mark6 recorder')
	parser.add_argument("recorder",type=str, help='the host name of the recorder to monitor')
	parser.add_argument("schedule",type=str, help='the name of the xml recording schedule')
	parser.add_argument("-p","--port", type=int, default=14242, help='Port on which cplane is listening (default 14242)"')

	args = parser.parse_args()

	# check that schedule file exists
        if not os.path.isfile(args.schedule):
                sys.exit ("schedule file does not exist: %s" % args.schedule)

	# connect to cplane
	mark6 = Mark6(args.recorder, args.port)	
	
	try:
		mark6.connect()
	except Exception as e:
		sys.exit(e.message)

	root = Tk()
	root.title("monitor")
	root.geometry("820x500")
	app = GUI(root, args, mark6)
	root.mainloop()
			
if __name__ == "__main__":
	main()
