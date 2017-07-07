# pylint: disable=C0103

""" This module contains the driver code for the QMG422 control box
for a pfeiffer mass-spectrometer. The code should in principle work
for multiple type of electronics. It has so far been tested with a
qme-125 box and a qme-??? box. The module is ment as a driver and
has very little function in itself. The module is ment to be used
as a sub-module for a large program providing the functionality to
actually use the mass-spectrometer.

Known bugs: Not all code has a proper distinction between the various
electronics. The qme-125 has many limitations compared to the qme-???
and these limitations are not always properly expressed in the code
or the output of the module
"""
from __future__ import print_function
import time
import logging
import serial
from PyExpLabSys.common.supported_versions import python2_and_3
python2_and_3(__file__)

LOGGER = logging.getLogger(__name__)
# Make the logger follow the logging setup from the caller
LOGGER.addHandler(logging.NullHandler())

class qmg_422(object):
    """ The actual driver class.  """
    def __init__(self, port='/dev/ttyS0', speed=19200):
        """ Initialize the module
        """
        self.serial = serial.Serial(port, speed, timeout=2.0)
        self.reverse_range = False
        self.type = '422'
        self.communication_mode(computer_control=True)

    def comm(self, command):
        """ Communicates with Baltzers/Pferiffer Mass Spectrometer

        Implements the low-level protocol for RS-232 communication with the
        instrument. High-level protocol can be implemented using this as a
        helper

        :param command: The command to send
        :type command: str
        :return: The reply associated with the last command
        :rtype: str
        """
        done = False
        iterations = 0
        while not done:
            iterations += 1
            LOGGER.debug("Command in progress: " + command)

            n = self.serial.inWaiting()
            if n > 0: #Skip characters that are currently waiting in line
                debug_info = self.serial.read(n)
                LOGGER.debug("Elements not read: " + str(n) + ": Contains: " + debug_info)

            ret = " "
            error_counter = 0
            while not ret[0] == chr(6):
                error_counter += 1
                command_text = command + '\r'
                LOGGER.debug('Command text: ' + command_text)
                self.serial.write(command_text.encode('ascii'))
                ret = self.serial.readline().decode()
                LOGGER.debug("Debug: Error counter: " + str(error_counter))
                LOGGER.debug("ret: " + str(ord(ret[0])))
                LOGGER.debug("Debug! In waiting: " + str(n))

                if error_counter == 3:
                    error = "Communication error: " + str(error_counter)
                    LOGGER.warning(error)
                if error_counter == 10:
                    LOGGER.error("Communication error: " + str(error_counter))
                if error_counter > 11:
                    LOGGER.error("Communication error! Quit program!")
                    quit()

            #We are now quite sure the instrument is ready to give back data
            self.serial.write(chr(5).encode('ascii'))
            ret = self.serial.readline().decode()

            LOGGER.debug("Number in waiting after enq: " + str(n))
            LOGGER.debug("Return value after enq:" + ret)
            LOGGER.debug("Ascii value of last char in ret: " + str(ord(ret[-1])))
            if (iterations > 1) and (iterations < 1000):
                LOGGER.info(iterations)
            if (ret[-1] == chr(10)) or (ret[-1] == chr(13)):
                ret_string = ret.strip()
                done = True
            else:
                LOGGER.info("Wrong line termination")
                LOGGER.info("Ascii value of last char in ret: "
                            + str(ord(ret[-1])))
                LOGGER.info('Value of string: ' + ret)
                time.sleep(0.5)
                self.serial.write(chr(5))
                ret = ' '
                while not ret[-1] == '\n':
                    ret += self.serial.read(1)
                #ret = self.serial.readline()
                ret_string = ret.strip()
                LOGGER.info("Ascii value of last char in ret: " +
                            str(ord(ret[-1])))
                LOGGER.info('Value of string: ' + ret)
                LOGGER.info('Returning: ' + ret_string)
                done = True
        return ret_string


    def communication_mode(self, computer_control=False):
        """ Returns and sets the communication mode.

        :param computer_control: Activates ASCII communication with the device
        :type computer_control: bool
        :return: The current communication mode
        :rtype: str
        """
        if computer_control:
            ret_string = self.comm('CMO ,1')
        else:
            ret_string = self.comm('CMO')
        comm_mode = ret_string

        if ret_string == '0':
            comm_mode = 'Console Keybord'
        if ret_string == '1':
            comm_mode = 'ASCII'
        if ret_string == '2':
            comm_mode = 'BIN'
        if ret_string == '3':
            comm_mode = 'Modem'
        if ret_string == '4':
            comm_mode = 'LAN'
        return comm_mode


    def simulation(self):
        """ Chekcs wheter the instruments returns real or simulated data

        :return: Message telling whether the device is in simulation mode
        :rtype: str
        """
        ret_string = self.comm('TSI ,0')
        if int(ret_string) == 0:
            sim_state = "Simulation not running"
        else:
            sim_state = "Simulation running"
        return sim_state

    def set_channel(self, channel):
        """ Set the current channel
        :param channel: The channel number
        :type channel: integer
        """
        self.comm('SPC ,' + str(channel)) #Select the relevant channel

    def read_sem_voltage(self):
        """ Read the SEM Voltage
        :return: The SEM voltage
        :rtype: str
        """
        sem_voltage = self.comm('SHV')
        return sem_voltage

    def read_preamp_range(self):
        """ Read the preamp range
        This function is not fully implemented
        :return: The preamp range
        :rtype: str
        """
        auto_range = self.comm('AMO')
        if auto_range in ('1', '2'):
            preamp_range = '0' #Idicates auto-range in mysql-table
        else:
            preamp_range = self.comm('ARA')
        return preamp_range

    def read_timestep(self):
        """ Reads the integration period of a measurement
        :return: The integration period in non-physical unit
        :rtype: str
        """
        # TODO: Make a look-up table to make the number physical
        timestep = self.comm('MSD')
        return timestep

    def sem_status(self, voltage=-1, turn_off=False, turn_on=False):
        """ Get or set the SEM status
        :param voltage: The wanted SEM-voltage
        :type voltage: integer
        :param turn_off: If True SEM will be turned on (unless turn_of==True)
        :type turn_off: boolean
        :param turn_on: If True SEM will be turned off (unless turn_on==True)
        :type turn_on: boolean
        :return: The SEM voltage, The SEM status, True means voltage on
        :rtype: integer, boolan
        """
        if voltage > -1:
            ret_string = self.comm('SHV ,' + str(voltage))
        else:
            ret_string = self.comm('SHV')
        sem_voltage = int(ret_string)

        if turn_off ^ turn_on: #Only accept self-consistent sem-changes
            if turn_off:
                self.comm('SEM ,0')
            if turn_on:
                self.comm('SEM ,1')
        ret_string = self.comm('SEM')
        sem_on = ret_string == "1"
        return sem_voltage, sem_on

    def emission_status(self, current=-1, turn_off=False, turn_on=False):
        """ Get or set the emission status.
        :param current: The wanted emission status. Only works for QME???
        :type current: integer
        :param turn_off: If True emission will be turned on (unless turn_of==True)
        :type turn_off: boolean
        :param turn_on: If True emission will be turned off (unless turn_on==True)
        :type turn_on: boolean
        :return: The emission value (for QME???), The emission status, True means filament on
        :rtype: integer, boolan
        """
        if current > -1:
            ret_string = self.comm('EMI ,' + str(current))
            emission_current = float(ret_string.strip())
        else:
            ret_string = self.comm('EMI')
            emission_current = float(ret_string.strip())

        if turn_off ^ turn_on:
            if turn_off:
                self.comm('FIE ,0')
            if turn_on:
                self.comm('FIE ,1')
        ret_string = self.comm('FIE')

        filament_on = ret_string == '1'
        return emission_current, filament_on


    def detector_status(self, SEM=False, faraday_cup=False):
        """ Choose between SEM and Faraday cup measurements"""
        if SEM ^ faraday_cup:
            if SEM:
                ret_string = self.comm('SDT ,1')
            if faraday_cup:
                ret_string = self.comm('SDT ,0')
        else:
            ret_string = self.comm('SDT')

        if int(ret_string) > 0:
            detector = "SEM"
        else:
            detector = "Faraday Cup"
        return detector


    def read_voltages(self):
        """ Read the qme-voltages """
        print("V01: " + self.comm('VO1')) #0..150,   1V steps
        print("V02: " + self.comm('VO2')) #0..125,   0.5V steps
        print("V03: " + self.comm('VO3')) #-30..30,  0.25V steps
        print("V04: " + self.comm('VO4')) #0..60,    0.25V steps
        print("V05: " + self.comm('VO5')) #0..450,   2V steps
        print("V06: " + self.comm('VO6')) #0..450,   2V steps
        print("V07: " + self.comm('VO7')) #0..250,   1V steps
        print("V08: " + self.comm('VO8')) #-125..125,1V steps
        print("V09: " + self.comm('VO9')) #0..60    ,0.25V steps

    def start_measurement(self):
        """ Start the measurement """
        self.comm('CRU ,2')

    def actual_range(self, amp_range):
        """ Returns the range that should be send to achieve the desired range """
        real_range = amp_range
        if self.reverse_range is True:
            if amp_range == -9:
                real_range = -11
            if amp_range == -10:
                real_range = -12
            if amp_range == -11:
                real_range = -9
            if amp_range == -12:
                real_range = -10
        return real_range

    def get_single_sample(self):
        """ Read a single sample from the device """
        samples = 0
        while samples == 0:
            try:
                status = self.comm('MBH')
            except:
                status = 'Error'
                LOGGER.error('Serial timeout, continuing measurement')
            LOGGER.info('Status: ' + str(status))
            try:
                status = status.split(',')
                samples = int(status[3])
            except:
                LOGGER.warn('Could not read status, continuing measurement')
            #time.sleep(0.05)
        try:
            value = self.comm('MDB')
        except:
            LOGGER.error('Error in MDB command')
            value = -1
        return value

    def get_multiple_samples(self, number):
        """ Read multiple samples from the device """
        values = [0] * number
        for i in range(0, number):
            values[i] = self.comm('MDB')
        return values


    def config_channel(self, channel, mass=-1, speed=-1, enable="", amp_range=0):
        """ Config a MS channel for measurement """
        self.comm('SPC ,' + str(channel)) #SPC: Select current parameter channel
        if mass > -1:
            self.comm('MFM ,' + str(mass))
        if speed > -1:
            self.comm('MSD ,' + str(speed))
        if enable == "yes":
            self.comm('AST ,0')
        if enable == "no":
            self.comm('AST ,1')

        if amp_range == 0:
            self.comm('AMO, 1')  #Auto range with lower limit
            # TODO: Lower limit should be read from config file
            self.comm('ARL, -11') # Lower auto range level
        else:
            self.comm('AMO, 0')  #Fix range
            self.comm('ARA, ' + str(self.actual_range(amp_range)))

        #Default values, not currently choosable from function parameters
        self.comm('DSE ,0')  #Use default SEM voltage
        self.comm('DTY ,1')  #Use SEM for ion detection
        self.comm('SDT ,1')  #Use SEM for ion detection
        #self.comm('DTY ,0')  #Use Faraday cup for ion detection
        #self.comm('SDT ,0')  #Use Faraday cup for ion detection
        self.comm('MMO ,3')  #Single mass measurement (opposed to mass-scan)
        self.comm('MRE ,15') #Peak resolution

    def measurement_running(self):
        """ Check if a measurement is running """
        error = 0
        while error < 10:
            status = self.comm('MBH')
            status = status.split(',')
            try:
                running = int(status[0])
                break
            except ValueError:
                error = error + 1
        if error < 9:
            return_val = running == 0
        else:
            return_val = False
        return return_val

    def waiting_samples(self):
        """ Return number of waiting samples """
        header = self.comm('MBH')
        header = header.split(',')
        number_of_samples = int(header[3])
        return number_of_samples

    def mass_scan(self, first_mass, scan_width, amp_range=0):
        """ Setup the mass spec for a mass scan """
        speed_list = {
            0: 0.0005,
            1: 0.001,
            2: 0.002,
            3: 0.005,
            4: 0.010,
            5: 0.020,
            6: 0.050,
            7: 0.1,
            8: 0.2,
            9: 0.5,
            10: 1,
            11: 2,
            12: 5,
            13: 10,
            14: 20,
            15: 60} # unit: [s/amu]
        speed = 9
        try:
            total_time = scan_width * speed_list[speed]
        except:
            total_time = -1

        if amp_range == 0:
            self.comm('AMO, 1')  #Auto range with lower limit
            # TODO: Lower limit should be read from config file
            self.comm('ARL, -11') # Lower auto range level
        else:
            self.comm('AMO, 0')  #Fix range
            self.comm('ARA, ' + str(self.actual_range(amp_range)))

        self.comm('CYM, 0') #0, single. 1, multi
        self.comm('SMC, 0') #Channel 0
        self.comm('DSE ,0') #Use default SEM voltage
        self.comm('DTY ,1') #Use SEM for ion detection
        self.comm('SDT ,1') #Use SEM for ion detection
        self.comm('MRE ,1') #Resolve peak
        self.comm('MMO, 0') #Mass scan, to enable FIR filter, set value to 1
        self.comm('MST, 1') #Steps 0: 1: 2: 64/amu
        self.comm('MSD, ' + str(speed)) #Speed
        self.comm('MFM, ' + str(first_mass)) #First mass
        self.comm('MWI, ' + str(scan_width)) #Scan width
        return total_time

    def mass_time(self, ns):
        """ Setup the mass spec for a mass-time measurement """
        self.comm('CYM ,1') #0, single. 1, multi
        self.comm('CTR ,0') #Trigger mode, 0=auto trigger
        self.comm('CYS ,1') #Number of repetitions
        self.comm('CBE ,1') #First measurement channel in multi mode
        self.comm('CEN ,' + str(ns)) #Last measurement channel in multi mod

if __name__ == '__main__':
    qmg = qmg_422()
    print(qmg.communication_mode(computer_control=True))
    print(qmg.read_voltages())
    print(qmg.detector_status())
    print(qmg.comm('SMR'))
    print('---')
    print('DTY: ' + qmg.comm('DTY')) # Signal source, 0: Faraday, 1: SEM
    print('DSE: ' + qmg.comm('SHV')) # SEM Voltage
    print('ECU: ' + qmg.comm('ECU'))
    print('SEM: ' + qmg.comm('SEM')) # SEM Voltage
    print('SQA: ' + qmg.comm('SQA')) # Type of analyzer, 0: 125, 1: 400, 4:200
    print('SMR: ' + qmg.comm('SMR')) # Mass-range, this needs to go in a config-file
    print('SDT: ' + qmg.comm('SDT')) # Detector type
    print('SIT: ' + qmg.comm('SIT')) # Ion source

