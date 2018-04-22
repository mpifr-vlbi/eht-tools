#!/usr/bin/env python

###########################################################################
#    Copyright (C) 2018  Helge Rottmann
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>
###########################################################################

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

	def __init__(self, parent, args, mark6):
		'''
		Constructor
		'''
		Frame.__init__(self, parent)
		self.parent=parent
		self.args = args
		self.mark6 = mark6
		self.scans = []
		self.showFutureScans = BooleanVar()
		self.showFutureScans.set(False)
		self.nextScan = -1

		self.initScanList()
		self.mk6InputStreams = self.mark6.getInputStreams()

		self.setupWidgets()

		self.updateClock()
		self.updateMark6State()
		self.update()

	def onChkShowFutureClick(self, event):
		self.update()

	def setupWidgets(self):
		"""	
		setup the widgets
		"""
		self.mk6Slot = []
		self.mk6Capacity = []

		self.parent.title("Mark6 monitor: %s" % (self.args.recorder))       

		self.parent.grid_rowconfigure(0,weight=1)
		self.parent.grid_columnconfigure(0,weight=100)
		self.parent.grid_columnconfigure(1,weight=1)
		self.parent.grid_rowconfigure(10,weight=100)
		self.parent.grid_columnconfigure(10,weight=1)
		self.parent.grid_rowconfigure(20,weight=1)
		self.parent.grid_columnconfigure(20,weight=1)
		#self.parent.config(background="lavender")


		# main frame
		mainFrame = LabelFrame(self.parent, text='')
		mainFrame.grid(row=0,column=0, columnspan=2, sticky='new')
		mainFrame.grid_columnconfigure(1,weight=10)

		schedFrame = LabelFrame(mainFrame, text='Schedule')
                schedFrame.grid(row=0,column=0, sticky="news")
		Label(schedFrame, text=os.path.basename(self.args.schedule), font=("Courier", 12)).grid(row=0,column=0, sticky=W)

		utcFrame = LabelFrame(mainFrame, text='')
		utcFrame.grid(row=1,column=0, sticky="news")
		self.clock = Label(utcFrame, font=('Courier', 24, 'bold') )
		self.clock.grid(row=0,column=0, sticky="news")

		mk6Frame = LabelFrame(mainFrame, text='Mark6')
		mk6Frame.grid(row=0,column=1, rowspan=2, sticky="news")
		
		for i in range(4):
			self.mk6Slot.append(  Button(mk6Frame, text="Slot", wraplength=60, bg="lawn green", width=7, height=4,disabledforeground="black",state=DISABLED))
			self.mk6Capacity.append ( Label(mk6Frame, font=('Courier', 8)))

		self.mk6Slot[0].grid(row=0,column=0, rowspan=2)
		self.mk6Slot[1].grid(row=0,column=1, rowspan=2)
		self.mk6Slot[2].grid(row=2,column=0, rowspan=2)
		self.mk6Slot[3].grid(row=2,column=1, rowspan=2)

		self.mk6Capacity[0].grid(row=0,column=2, sticky=W)
		self.mk6Capacity[1].grid(row=1,column=2, sticky=W)
		self.mk6Capacity[2].grid(row=2,column=2, sticky=W)
		self.mk6Capacity[3].grid(row=3,column=2, sticky=W)


		# Define widgets in the options frame
		optionsFrame = LabelFrame(self.parent, text='Options')
		optionsFrame.grid(row=20,column=0, columnspan=2, sticky='new')

		self.chkShowFuture = Checkbutton(optionsFrame, text = "show future scans", variable =  self.showFutureScans)
		self.chkShowFuture.grid(row=0,column=0, columnspan=2,sticky='ew')
		self.chkShowFuture.bind("<ButtonRelease-1>", self.onChkShowFutureClick)



		# treeview frame

		self.tree = ttk.Treeview( self.parent, columns=('tick','source', 'start', 'stop', 'duration','gaptime', 'status'))

		self.tree.heading('#0', text='+',anchor=W)
		self.tree.heading('#1', text='scan')
		self.tree.heading('#2', text='source')
		self.tree.heading('#3', text='start')
		self.tree.heading('#4', text='stop')
		self.tree.heading('#5', text='duration [s]')
		self.tree.heading('#6', text='gap [s]')
		self.tree.heading('#7', text='status', anchor=W)
		self.tree.column('#0', width=0,stretch=NO)
		self.tree.column('#1', width=160,stretch=NO)
		self.tree.column('#2', width=130, stretch=NO)
		self.tree.column('#3', width=130, stretch=NO)
		self.tree.column('#4', width=130, stretch=NO)
		self.tree.column('#5', width=70, stretch=NO)
		self.tree.column('#6', width=70, stretch=NO)
		self.tree.column('#7', stretch=YES)
		self.tree.grid(row=10, column=0, sticky='nesw')

		#scrollbar 
		vsb = ttk.Scrollbar(orient="vertical",command=self.tree.yview)
		self.tree.configure(yscrollcommand=vsb.set)
		vsb.grid(row=10, column=1, sticky='ns')

		# color code the lines based on status field
		self.tree.tag_configure('missing', background='salmon')
		self.tree.tag_configure('pending', background='yellow')
		self.tree.tag_configure('OK', background='green yellow')
		self.tree.tag_configure('Error', background='red')
		self.tree.tag_configure('recording', background='green')

	
	
	def updateMark6State(self):

		self.mark6.readSlotInfo()
		self.mk6InputStreams = self.mark6.getInputStreams()
		
		msg = ""

		streamSlots = []
		groupSlots = []
		activeSlots = []

		# check the input_streams
		if len(self.mk6InputStreams) == 0:
			msg += "No input streams defined"
		for stream in self.mk6InputStreams:
			streamSlots += list(stream['slots'])
			

		# check if all modules are activated and the number of discovered disks is 8
		for i in range(4):
			error = 0
			capacityStr = "Slot {:d} capacity [TB] (free/total): {:.1f} / {:.1f}"

			if self.mark6.slots[i].vsn == "unknown":
				self.mk6Slot[i]["text"] = "inactive"
				capacityStr = capacityStr.format(i, 0, 0)
				error += 1
			
				if str(i+1) in streamSlots:
					msg += "Required (by stream) slot {:d} is currently inactive\n".format(i+1)
			else:
				activeSlots.append(i+1)

				if self.mark6.slots[i].numDisksDiscovered != 8 or self.mark6.slots[i].numDisksRegistered != 8:
					error += 1
					msg += "Module {} (slot {}): less than 8 disks found\n".format(self.mark6.slots[i].vsn, i+1)
				groupSlots += list(map(int, self.mark6.slots[i].group))

                                self.mk6Slot[i]["text"] = "{}\n{:.1f}%".format(self.mark6.slots[i].vsn,  self.mark6.slots[i].freePercentage)
				capacityStr = capacityStr.format(i, self.mark6.slots[i].groupCapacityGB/1000, self.mark6.slots[i].capacityRemainingGB/1000)

			self.mk6Capacity[i]["text"] = capacityStr
			# change color to red in case of error
			if error > 0:
				self.mk6Slot[i]["bg"] = "red"
	
		# verify that all slots requested by the group are active
		groupSlots = list(set(groupSlots))
		for i in groupSlots:
			if i not in activeSlots:
				msg += "Required (by group) slot {:d} is currently inactive\n".format(int(i)+1)


		if len(msg) > 0:
			tkMessageBox.showerror("Error", msg)

		self.mk6Slot[0].after(10000, self.updateMark6State)



		

	def updateClock(self):
		global time1
		# get the current local time from the PC
		timeStr = datetime.utcnow().strftime('%H:%M:%S')
		self.clock.config(text=timeStr)
		self.clock.after(300, self.updateClock)
			
	def update(self):
		"""
		update the scan state and refresh the table
		This method is refreshed based on the schedule
		"""

		self.nextScan, future = self.updateScanList()
		sleepUntil = None

		# disable chkbox if no future scans to come
		if (future == 0):
			self.chkShowFuture['state'] = DISABLED
		else:
			self.chkShowFuture['state'] = NORMAL
		
		
		# clear the treeview
		self.tree.delete(*self.tree.get_children())


		for scan in self.scans:
			idx = self.scans.index(scan)

			if scan['tense'] == 1 and idx != self.nextScan and self.showFutureScans.get() == False:
				continue
			# script was started in the middle of a running scan
			if scan["tense"] == 0:
				sleepUntil = scan['stopDateTime'] + timedelta(seconds=5)
				marker = "+"
			elif idx == self.nextScan: 
				sleepUntil = scan['startDateTime'] + timedelta(seconds=5)
				marker = "+"
			else:
				marker = " "

			gapMin = scan["gapTime"]

			self.tree.insert('', 0, text=marker, values=(scan["name"], scan["source"], scan["startTimeStr"], scan["stopTimeStr"], scan["duration"], gapMin, scan['status']), tags=(scan["status"]))



		# sleep  until next scans finishes or current one stops recording
		if sleepUntil:
			print "sleeping until %s" % sleepUntil.strftime("%H:%M:%S")
			self.parent.after((sleepUntil - datetime.utcnow()).seconds*1000, self.update)
		


	def updateScanList(self):
		'''
		update the scan list (status, sizes) based on the recorder feedback

		Returns:
			int: the index of the scan upcoming next in the schedule
			int: the number of future scans
		'''

		self.mark6.readScanList()

		candidate = ""
		
		next = -1
		future = 0
		for scan in self.scans:
			idx = self.scans.index(scan)

			dtNow = datetime.utcnow()

			if scan['stopDateTime'] < dtNow:      # past scan
			
				scan['tense'] = -1	#past	
				recFilename = "%s_%s_%s" %(scan['exp'],scan['station'],scan['name'])
				recScan = self.mark6.getScanByName(recFilename)

				if recScan:
					scan['recSize'] = recScan.size
					scan['status'] = 'OK'
				else:
					scan['recSize'] = 0
					scan['status'] = 'missing'

			elif scan['startDateTime'] < dtNow and scan['stopDateTime'] > dtNow:   # scan should be recording now

				scan['tense'] = 0	#present

				recState = self.mark6.getRecordingState()
				if recState['state'] == "recording":
					scan['status'] = state
				else: # scan should be recording but is not
					# only show error once
					if scan['status'] != "Error":
						tkMessageBox.showerror("Error", "scan %s is not recording on %s" % (scan['name'], self.args.recorder))
						scan['status'] = "Error"
				next = idx

			elif  scan['startDateTime'] > dtNow:	# future scan
				scan['tense'] = 1	#future

				future =+ 1

				# first future scan
				if next == -1:
					# check if scheduled
					recState = self.mark6.getRecordingState()
					if recState['state'] == 'pending' or recState['state'] == 'off':
						scan['status'] = "pending"
					
					next = idx

		return next, future

	def initScanList(self):

		tree = ET.parse(self.args.schedule)
		root = tree.getroot()

		for scan in root.findall("scan"):
			scanInfo = {}
			duration = int(scan.get('duration'))
			scanName = scan.get('scan_name').strip()
			station = scan.get('station_code').strip()
			exp = scan.get('experiment').strip()
			startTime = scan.get('start_time')

			dtStart = datetime.strptime(startTime, '%Y%j%H%M%S')
			dtStop = dtStart + timedelta(seconds=duration)
			dtNow = datetime.utcnow()

			#recFilename = "%s_%s_%s" %(exp,station,scanName)
			#recScan = mark6.getScanByName(recFilename)

			scanInfo['name'] = scanName
			scanInfo['station'] = station
			scanInfo['exp'] = exp
			scanInfo['duration'] = duration
			scanInfo['startTimeStr'] = dtStart.strftime('%Y-%j %H:%M:%S')
			scanInfo['stopTimeStr'] = dtStop.strftime('%Y-%j %H:%M:%S')
			scanInfo['startDateTime'] = dtStart
			scanInfo['stopDateTime'] = dtStop
			scanInfo['recsize'] = 0
			scanInfo['source'] = scan.get('source')
			scanInfo['status'] = ""
			scanInfo['tense'] = -1	# 1=future,0=present,-1=past


			self.scans.append(scanInfo)

		# calculate the gap times
		for i in range(len(self.scans)-1):
			self.scans[i]["gapTime"] = (self.scans[i+1]['startDateTime'] - self.scans[i]['stopDateTime']).total_seconds()

		# last scan has empty gap time
		self.scans[-1]['gapTime'] = ""

		return


def getRecordedScans(mark6):
	mark6.readScans()

	return mark6.scans

def getRecordedScanSize(scanname, files):

	for file in files:
		size, name = file.split()
		if os.path.splitext(name)[0] == scanname:
			return int(size)
	return -1


				

		
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
	root.title("mark6 schedule monitor")
	root.geometry("820x500")
	app = GUI(root, args, mark6)
	root.mainloop()
			
if __name__ == "__main__":
	main()
