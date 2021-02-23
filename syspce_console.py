# -*- coding: utf-8 -*-

import logging
import json
import os
import re
import pprint
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.shortcuts import CompleteStyle, prompt

from syspce_message import *


log = logging.getLogger('sysmoncorrelator')



class Console(object):
    ''' Console user module '''

    def __init__(self, data_buffer_in,
                                       data_condition_in,
                                       output_lock):


        self.data_buffer_in = data_buffer_in
        self.data_condition_in = data_condition_in

        self._running = False
        self.name = 'Console'
        self.module_id = Module.CONSOLE
        self.output_lock = output_lock

        # First message to console , current jobs started
        self.send_message(MessageSubType.SHOW_JOBS,
                                          Module.CONTROL_MANAGER, [])


        self.console_history = FileHistory('history.dat')
        self.session = PromptSession(history=self.console_history,
                                                                 auto_suggest=AutoSuggestFromHistory(),
                                                                 enable_history_search=True)

        self.syspce_completer = WordCompleter(
                        [
                                "run",
                                "jobs",
                                "stop_job",
                                "show_config",
                                "show_alerts",
                                "stats",
                                "set",
                                "info",
                                "ps",
                                "exit",
                        ],
                        meta_dict={
                                "run": "Run actions based on syspce config",
                                "jobs": "Show current active Jobs",
                                "set": "[var] [value] Sets config parameters",
                                "stop_job": "[JobId] Stops a Job by job name",
                                "show_config": "Show current config",
                                "show_alerts": "Show alerts detected",
                                "stats": "List statistics for hostsnames",
                                "info": "[pid] [eventid] [computer] Show eventid details from a process",
                                "ps": "[tree_id] [computer] Processes list, treeid and computer is optional",
                                "exit": "Bye bye",
                        },
                        ignore_case=True,
                        )


    def run(self):
        ''' Thread console main code'''

        self._running = True
        log.debug("%s working..." % (self.name))

        while self._running:
            try:
                #command = unicode(raw_input("SYSPCE#>"), 'utf-8')

                command = self.session.prompt('SYSPCE#>',
                                                completer=self.syspce_completer,
                                                complete_style=CompleteStyle.MULTI_COLUMN)

            except ValueError as e:
                print("Input error: %s" % str(e))
                command = "exit"

            if (command == "jobs"):
                self.send_message(MessageSubType.SHOW_JOBS,
                                                  Module.CONTROL_MANAGER, [])

            elif(re.match("^run", command)):
                self.send_message(MessageSubType.RUN,
                                                  Module.CONTROL_MANAGER, [])
                self.s_print('Runnig actions in config...')

            elif(re.match("^stats", command)):
                self.send_message(MessageSubType.STATS,
                                                  Module.CONTROL_MANAGER, [])
                self.s_print('Runnig stats')

            elif(("show commands" in command) or ("help" in command)):
                self.help()

            elif(re.match("^show_config", command)):
                self.send_message(MessageSubType.SHOW_CONFIG,
                                                  Module.CONTROL_MANAGER, [])

            elif(re.match("^stop_job ", command)):
                try:
                    job_name = command.split('stop_job ')[1].replace(' ','')
                    self.send_message(MessageSubType.STOP_JOB,
                                                      Module.CONTROL_MANAGER, [job_name])
                except Exception as e:
                    self.s_print('Command error %s' % e)

            elif(re.match("^set", command)):
                c_splited = self.get_params(command)
                try:
                    var = c_splited[1]
                    value = c_splited[2]
                    self.send_message(MessageSubType.SET_CONFIG,
                                                      Module.CONTROL_MANAGER,
                                                      [var, value])

                except Exception as e:
                    self.s_print('Command error %s' % e)

            elif(re.match("^info", command)):
                try:
                    c_splited = self.get_params(command)
                    n_params = len(c_splited)

                    if n_params == 4:
                        pid = c_splited[1]
                        eventid = c_splited[2]
                        computer = c_splited[3]

                    elif n_params == 3:
                        pid = c_splited[1]
                        eventid = c_splited[2]
                        computer = ''

                    elif n_params == 2:
                        pid = c_splited[1]
                        eventid = '1'
                        computer = ''

                    self.send_message(MessageSubType.INFO_EVENTID,
                                                      Module.CONTROL_MANAGER,
                                                      [pid ,eventid, computer])

                except Exception as e:
                    self.s_print('Command error %s' % e)

            elif(re.match("^ps", command)):
                self.s_print("\nGetting Process/Sessions list...\n")
                try:
                    c_splited = self.get_params(command)
                    if len(c_splited) == 3:
                        tree_id = c_splited[1]
                        computer = c_splited[2]
                    else:
                        tree_id = '-1'
                        computer = ''

                    self.send_message(MessageSubType.PS,
                                                      Module.CONTROL_MANAGER,
                                                      [tree_id, computer])

                except Exception as e:
                    self.s_print('Command error %s' % e)

            elif(command == "exit" or command == "quit"):
                self.terminate()
                self.quit()


        log.debug("%s terminated." % (self.name))

    ## COMMAND METHODS
    ##################

    def help(self):
        ''' Basic console help message'''

        help = '''
         ---------------------------------------------------------------------------------------------------
        |HELP                                                                                              |
         ---------------------------------------------------------------------------------------------------

        COMMANDS
        --------
        jobs                            - Show current active Jobs
        stop_job <Name>                 - Stops a Job by job name
        set <Var> <Name>                - Stops a Job by job name
        ps [treeid] [computer]          - Processes list, treeid and computer is optional
        info <pid> [eventid] [computer] - Show eventid details from a process
        help                            - List commads helps
        show_config                     - Show current config
        show_alerts                     - Show alerts detected
        stats                           - List statistics for hostnames
        exit|quit                       - Bye bye.
        '''
        self.s_print(help)

    def quit(self):
        ''' Terminate all modules and program execution
        '''
        self.send_message(MessageSubType.TERMINATE, Module.ENGINE_MANAGER, [])
        self.send_message(MessageSubType.TERMINATE, Module.INPUT_MANAGER, [])
        self.send_message(MessageSubType.TERMINATE, Module.CONTROL_MANAGER, [])

    ## ADDITIONAL METHODS
    #####################

    def send_message(self, subtype, destination, payload):
        ''' General method for communication with other modules
        '''
        message = Message(self.data_buffer_in, self.data_condition_in)
        message.send(MessageType.COMMAND,
                                         subtype,
                                         Module.CONSOLE,
                                         destination,
                                         Module.CONSOLE,
                                         payload)

    def print_search_result(self, results):
        self.s_print(pprint.pformat(results))

    def print_alert_hierarchy(self, alerts):
        for alert in alerts:
            self.s_print(alert)

    def print_alert_baseline(self, alerts):
        self.s_print(alerts)

    def print_command_result(self, result):
        self.s_print(result)

    def print_notification(self, results):
        self.s_print("\nNOTIFICATION RES: %s" % results)

    def s_print(self, string):
        ''' Safe print method avoiding collisions when printing out to
                console
        '''
        self.output_lock.acquire()
        print(string)
        self.output_lock.release()

    def get_params(self, commadline):
        p_list = []

        cl_splited = commadline.split(' ')
        for param in cl_splited:
            if not ' ' in param and param != '':
                param = param.replace('\r', '')
                p_list.append(param)
        return p_list

    def terminate(self):
        self._running = False
        log.debug("%s ending..." % (self.name))
