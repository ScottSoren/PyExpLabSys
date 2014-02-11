import threading
import Queue
import time
#import matplotlib.pyplot as plt
import MySQLdb
import curses
import logging
import socket

import sys
sys.path.append('../')
import SQL_saver

import qmg_status_output
import qmg_meta_channels

#import qmg420
import  qmg422

class qms():

    def __init__(self, qmg, sqlqueue=None, loglevel=logging.ERROR):
        self.qmg = qmg
        if not sqlqueue == None:
            self.sqlqueue = sqlqueue
        else: #We make a dummy queue to make the program work
            self.sqlqueue = Queue.Queue()
        self.operating_mode = "Idling"
        self.current_action = 'Idling'
        self.message = ''
        self.autorange = False
        self.current_timestamp = "None"
        self.measurement_runtime = 0
        self.stop = False
        self.chamber = 'dummy'
        self.channel_list = {}
        
        #Clear log file
        with open('qms.txt', 'w'):
            pass
        logging.basicConfig(filename="qms.txt", level=logging.INFO)
        logging.info("Program started. Log level: " + str(loglevel))
        logging.basicConfig(level=logging.INFO)
        

    def communication_mode(self, computer_control=False):
        return self.qmg.communication_mode(computer_control)

    def emission_status(self, current=-1, turn_off=False, turn_on=False):
        return self.qmg.emission_status(current, turn_off, turn_on)

    def sem_status(self, voltage=-1, turn_off=False, turn_on=False):
        return self.qmg.sem_status(voltage, turn_off, turn_on)

    def detector_status(self, SEM=False, faraday_cup=False):
        return self.qmg.detector_status(SEM, faraday_cup)

    def read_voltages(self):
        self.qmg.read_voltages()

    def simulation(self):
        """ Chekcs wheter the instruments returns real or simulated data """
        self.qmg.simulation()

    def config_channel(self, channel, mass=-1, speed=-1, amp_range=0, enable=""):
        self.qmg.config_channel(channel, mass=mass, speed=speed, amp_range=amp_range, enable=enable)


    def create_mysql_measurement(self, channel, timestamp, masslabel, comment,
                                 metachannel=False, type=5):
        """ Creates a MySQL row for a channel.
        
        Create a row in the measurements table and populates it with the
        information from the arguments as well as what can be
        auto-generated.
        
        """
        cnxn = MySQLdb.connect(host="servcinf", user=self.chamber, 
                               passwd=self.chamber, db="cinfdata")

        cursor = cnxn.cursor()
        
        if not metachannel:
            self.qmg.set_channel(channel)
            sem_voltage = self.qmg.read_sem_voltage()
            preamp_range = self.qmg.read_preamp_range()
            timestep = self.qmg.read_timestep()   #TODO: We need a look-up table, this number is not physical
        else:
            sem_voltage = "-1"
            preamp_range = "-1"
            timestep = "-1"
                
        query = ""
        query += 'insert into measurements_' + self.chamber + ' set mass_label="' 
        query += masslabel + '"'
        query += ', sem_voltage="' + sem_voltage + '", preamp_range="'
        query += preamp_range + '", time="' + timestamp + '", type="' + str(type) + '"'
        query += ', comment="' + comment + '"'

        cursor.execute(query)
        cnxn.commit()
        
        query = 'select id from measurements_' + self.chamber + ' order by id desc limit 1'
        cursor.execute(query)
        id_number = cursor.fetchone()
        id_number = id_number[0]
        cnxn.close()
        return(id_number)

    def create_ms_channellist(self, channel_list, timestamp, no_save=False):
        """ This function creates the channel-list and the associated mysql-entries """
        #TODO: Implement various ways of creating the channel-list
        #TODO: Implement version 2.0 of autorange with deeper autorange
        ids = {}
        
        for i in range(0,16):
            self.config_channel(i, mass=99, speed=1, amp_range=-1,enable='no')

        comment = channel_list[0]['comment']
        self.autorange = channel_list[0]['autorange']
        logging.info('Autorange: ' + str(self.autorange))
        #Check for qmg-version 422 will do hardware autorange!

        for i in range(1,len(channel_list)):
            ch = channel_list[i]
            self.config_channel(channel=i, mass=ch['mass'], speed=ch['speed'], amp_range=ch['amp_range'], enable="yes")
            self.channel_list[i] = {'masslabel':ch['masslabel'],'value':'-'}
            
            if no_save == False:
                ids[i] = self.create_mysql_measurement(i,timestamp,ch['masslabel'],comment)
            else:
                ids[i] = i
        ids[0] = timestamp
        logging.error(ids)
        return ids
        
    def mass_time(self,ms_channel_list, timestamp):
        self.operating_mode = "Mass Time"
        self.stop = False
        ns = len(ms_channel_list) - 1
        self.qmg.mass_time(ns)

        start_time = time.time()
        ids = self.create_ms_channellist(ms_channel_list, timestamp, no_save=False)
        self.current_timestamp = ids[0]
        
        while self.stop == False:
            if self.autorange:
                for i in range(1, ns+1):
                    #TODO: Decrease measurement time during autorange
                    self.config_channel(channel=i, amp_range=4)
                self.qmg.set_channel(1)
                self.qmg.start_measurement()
                time.sleep(0.1)
                ranges = {}
                autorange_complete = False
                while not autorange_complete:
                    for i in range(1, ns+1):
                        value = self.qmg.get_single_sample()
                        #logging.info(value)
                        try:
                            value = float(value)
                        except:
                            logging.warn('Missing value during auto-range')
                            autorange_complete = False
                            break
                        if value>0.9:
                            ranges[i] = 2
                        if (value<0.9) and (value>0.09):
                            ranges[i] = 4
                        if (value<0.09) and (value>0.009):
                            ranges[i] = 5
                        if (value<0.009) and (value>0.0009):
                            ranges[i] = 6
                        if value < 0.0009:
                            ranges[i] = 7
                        autorange_complete = True
                if autorange_complete:
                    for i in range(1, ns+1):
                        self.config_channel(channel=i, amp_range=ranges[i])
                        ms_channel_list[i]['amp_range'] = ranges[i]
                        #logging.info('Value: ' + str(value) + '  Range: ' + str(ranges[i]))
    
            self.qmg.set_channel(1)
            self.qmg.start_measurement()
            time.sleep(0.1)
            for channel in range(1, ns+1):
                self.measurement_runtime = time.time()-start_time
                value = self.qmg.get_single_sample()
                self.channel_list[channel]['value'] = value
                sqltime = str((time.time() - start_time) * 1000)
                if value == "":
                    break
                else:
                    value = float(value)
                    if self.qmg.type == '420':
                        value = value / 10**(ms_channel_list[channel]['amp_range']+5)
                    query  = 'insert into '
                    query += 'xy_values_' + self.chamber + ' '
                    query += 'set measurement="' + str(ids[channel])
                    query += '", x="' + sqltime + '", y="' + str(value) + '"'
                self.sqlqueue.put(query)
                time.sleep(0.25)
            time.sleep(0.1)
        self.operating_mode = "Idling"
        

    def mass_scan(self, first_mass=0, scan_width=50, comment='Mass-scan'):
        start_time = time.time()
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        self.operating_mode = 'Mass-scan'
        id = self.create_mysql_measurement(0,timestamp,'Mass Scan',comment, type=4)
        self.message = 'ID number: ' + str(id) + '. Scanning from ' + str(first_mass) + ' to ' + str(first_mass+scan_width) + 'amu'
        self.current_timestamp = timestamp
        self.qmg.mass_scan(first_mass, scan_width)

        self.measurement_runtime = time.time()-start_time

        self.qmg.start_measurement()
        self.current_action = 'Performing scan'
        time.sleep(0.1) #Allow slow qmg models time to start measurement
        while self.qmg.measurement_running():
            self.measurement_runtime = time.time()-start_time
            time.sleep(1)

        start = time.time()
        number_of_samples = self.qmg.waiting_samples()
        samples_pr_unit = 1.0 / (scan_width/float(number_of_samples))

        query  = '' 
        query += 'insert into xy_values_' + self.chamber 
        query += ' set measurement = ' + str(id) + ', x = '
        self.current_action = 'Downloading samples from device'
        j = 0
        for i in range(0,number_of_samples/100):
            self.measurement_runtime = time.time()-start_time
            samples = self.qmg.get_multiple_samples(100)
            for i in range(0,len(samples)):
                j += 1
                new_query = query + str(first_mass + j / samples_pr_unit) + ', y = ' + str(samples[i])
                self.sqlqueue.put(new_query)
        samples = self.qmg.get_multiple_samples(number_of_samples%100)
        for i in range(0,len(samples)):
            j += 1
            new_query = query + str(first_mass + j / samples_pr_unit) + ', y = ' + str(samples[i])
            self.sqlqueue.put(new_query)

        self.current_action = 'Emptying Queue'
        while not self.sqlqueue.empty():
            self.measurement_runtime = time.time()-start_time
            time.sleep(0.1)
        time.sleep(0.5)
        
if __name__ == "__main__":
    sql_queue = Queue.Queue()
    sql_saver = SQL_saver.sql_saver(sql_queue,'dummy')
    sql_saver.daemon = True
    sql_saver.start()

    qmg = qmg422.qmg_422()

    qms = qms(qmg, sql_queue)
    qms.communication_mode(computer_control=True)
    printer = qmg_status_output.qms_status_output(qms,sql_saver_instance=sql_saver)
    printer.daemon = True
    printer.start()
    #qms.mass_scan(0,50,comment = 'Test scan - qgm422')


    channel_list = {}
    channel_list[0] = {'comment':'leaktesting', 'autorange':True}
    #channel_list[1] = {'mass':1.6,'speed':9, 'masslabel':'M2'}
    channel_list[1] = {'mass':4,'speed':9, 'masslabel':'M4'}
    channel_list[2] = {'mass':7,'speed':9, 'masslabel':'M7'}
    #channel_list[4] = {'mass':11.4,'speed':9, 'masslabel':'M12'}
    #channel_list[5] = {'mass':13.4,'speed':9, 'masslabel':'M14'}
    #channel_list[6] = {'mass':17.4,'speed':9, 'masslabel':'M18'}
    #channel_list[1] = {'mass':27,'speed':9, 'masslabel':'M27'}
    #channel_list[8] = {'mass':31.4,'speed':9, 'masslabel':'M32'}
    #channel_list[9] = {'mass':43.4,'speed':9, 'masslabel':'M44'}"""
    #channel_list[2] = {'mass':28,'speed':9,'masslabel':'M28'}
    #channel_list[3] = {'mass':29,'speed':9,'masslabel':'M29'}


    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    #meta_udp = qmg_meta_channels.udp_meta_channel(qmg, timestamp, channel_list[0]['comment'], 5)
    #meta_udp.create_channel('Temperature', 'rasppi19', 9990, 'read_global_temp')
    #meta_udp.create_channel('Chamber pressure', 'rasppi19', 9990, 'read_global_pressure')
    #meta_udp.create_channel('HPC, Temperature', 'rasppi19', 9990, 'read_hp_temp')
    #meta_udp.create_channel('HPC, Pirani', 'rasppi13', 9999, 'read_pirani')
    #meta_udp.create_channel('HPC, Pressure Controller', 'rasppi13', 9999, 'read_pressure')
    #meta_udp.daemon = True
    #meta_udp.start()



    print qmg.mass_time(channel_list, timestamp)

    time.sleep(1)
    printer.stop()

    #print qmg.read_voltages()
    #print qmg.sem_status(voltage=2200, turn_on=True)
    #print qmg.emission_status(current=0.1,turn_on=True)
    #print qmg.qms_status()
