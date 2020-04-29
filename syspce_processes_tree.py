import logging
import threading
import datetime

from syspce_parser import get_image_fileName

log = logging.getLogger('sysmoncorrelator')


class ProcessesTree(object):

	def __init__(self):
		self.processes_tree = {}
		self.tree_condition_in = threading.Condition()
		self.detection_macros = []
		self.actions_matched = {}

	def set_macros(self, detection_macros):
		self.detection_macros = detection_macros

	def pre_process_events(self, events_list):
		'''Method for adding more info to Sysmon events'''

		i = 0
		while i < len(events_list):

			# Checking if correct information is provided
			if not 'idEvent' in events_list[i]:
				events_list.pop(i)

			# Adding new atribute alert to all actions, used later for presenting
			#results
			events_list[i]['Alert'] = False

			if events_list[i]['idEvent'] == 1: 
			
				ParentImage	= events_list[i]['ParentImage']		
				ParentProcessId	= events_list[i]['ParentProcessId']	

				# Adding 2 new attribites to Event id 1
				# CreationType: [RegularThread, InjectedThread] 
				# 	(see update_process_creation_origin) and
				# RealParent: real parent process which created current process
			
				parent = "(" + ParentProcessId + ") " + ParentImage
				c_origin = {"CreationType":"RegularThread", "RealParent":parent}	
				events_list[i].update(c_origin)	
			
				# Adding new attribute process TTL
				process_ttl = {"ProcessTTL": "Running"}	
				events_list[i].update(process_ttl)

			i += 1

		return events_list

	def add_event_to_tree(self, req):
		''' Adds one event to processes tree'''		
		node = None

		if not req['computer'] in self.processes_tree:
			self.processes_tree[req['computer']] = {}

		computer_ptree = self.processes_tree[req['computer']]
		ProcessGuid = req['ProcessGuid']

		# Now processin message type 1 or other type 3,5...
		# Message type 1 , used for building tree's skeleton 
		if req['idEvent'] == 1: 
			
			# Tree Node with process datails
			node = Node_(req)

			#Lo asignamos a la root de ese equipo ya que no existia con 
			#anterioridad el host
			node.acciones['1'].append(req)
			computer_ptree[ProcessGuid] = node
	

		# Es otra accion diferente a la creacion de un proceso
		else:

			if (not req['computer'] in self.processes_tree):
				return node
	
			# Adding now normal proccess action if exists
			if req['ProcessGuid'] in computer_ptree:				
				node = computer_ptree[req['ProcessGuid']]

				# Adding additional information regarding target 
				if req['idEvent'] == 8 or req['idEvent'] == 10:

					if computer_ptree.has_key(req['TargetProcessGuid']):
						tnode = computer_ptree[req['TargetProcessGuid']]

						req['TargetSession'] = tnode.acciones['1'][0]['TerminalSessionId']
						req['TargetIntegrityLevel'] = tnode.acciones['1'][0]['IntegrityLevel']
						req['TargetUser'] = tnode.acciones['1'][0]['User']
										
					# if tnode dosen't exists we don't include new attribites
						
				# Adding additional information regarding source 
				if req['idEvent'] == 108 or req['idEvent'] == 110:

					if computer_ptree.has_key(req['SourceProcessGuid']):
						snode = computer_ptree[req['SourceProcessGuid']]
						req['SourceSession'] = \
									snode.acciones['1'][0]['TerminalSessionId']
						req['SourceIntegrityLevel'] = \
									snode.acciones['1'][0]['IntegrityLevel']
						req['SourceUser'] = \
									snode.acciones['1'][0]['User']
										
					# if snode dosen't exists we don't include new attribites
				eventid = str(req['idEvent'])
				node.acciones[eventid].append(req)
										
				# 2 types: regular or by remote injected thread
				node.update_process_creation_origin(req, computer_ptree)					

				#If it's a Terminate proccess (5) event let's calculate TTL
				if req['idEvent'] == 5:
					process_ttl = {"ProcessTTL": str(node.getLiveTime())}	
					node.acciones['5'][0].update(process_ttl)	
					node.acciones['1'][0].update(process_ttl)


		return node

	def get_candidates(self, ptree, process_list, filter_dicc):
		''' Return a proccesses that match event criteria'''

		matchlist = []

		self.actions_matched = {}

		for process in process_list:
			match = True

			for type_action in filter_dicc.keys():
				match =  self._check_action(type_action, ptree[process], filter_dicc)
				if not match:
					break
					
			if match:		
				matchlist.append(process)

		return matchlist


	def get_direct_childs(self, ptree, process_list):
		''' Return a proccesses that match event criteria'''

		plist = []

		for process_guid in process_list:
			plist += self._get_childs(ptree, process_guid)

		return plist

	def _get_childs(self, ptree, process_guid):
		childs_list = []

		for child_reg in ptree[process_guid].childs:
			childs_list.append(child_reg['ChildProcessGuid'])

		return childs_list

	def get_all_childs(self, ptree, process_list, res_list):
		''' Return a proccesses that match event criteria'''

		for process_guid in process_list:
			process_list = self._get_childs(ptree, process_guid)
			res_list += process_list
			self.get_all_childs(ptree,process_list, res_list)
		

	def _check_action(self, type_action, nodo, filter_list): 

		'''Method that checks rule acctions (1,3...) against process acctions
		'''			
		#  Acction types could have "c" (continue) and "-" (reverse, not)
		# modifiers let's remove them, Example:
		# {"1c":{"Image":"winword"},"-3":{"Image":"winword"}}


		t_action = type_action.replace('c','')

		if "-" in type_action:
			t_action = t_action.replace('-','')
			acction_reverse = True
		else:
			acction_reverse = False
			
		if (nodo.acciones[t_action] != []):   

			# Checking all specific acctions from a process
			for acc in nodo.acciones[t_action]:
				# Getting all the filters from a rule
				
				result = True
				
				for filter in filter_list[type_action]:
				
					# Filter property could have "-" modifier as well
					acc_filter = filter.replace('-','')
					if "-" in filter:
						filter_reverse = True		
					else:
						filter_reverse = False
					
					final_reverse = acction_reverse^filter_reverse
					
					# Finally comparing if a rule filter match a process action
					if not (acc.has_key(acc_filter)) or \
								not self._check_filter_match( 
											filter_list[type_action][filter], 
											acc[acc_filter], final_reverse):
						
						result =  False
						break
						
				if result:
					if self.actions_matched.has_key(nodo.guid):
						self.actions_matched[nodo.guid].append(acc)
					else:
						self.actions_matched.update({nodo.guid:[acc]})
						
					return True
					
		# Process has no acctions of this type
		else:
			if acction_reverse:
				return True
		
		return False
		
	'''Method that compares if a rule filter match a process acction
	'''
	def _check_filter_match(self, filter, acction, reverse):
		match = False
		
		if filter in self.detection_macros:
			filter_list =  self.detection_macros[filter]
		else:
			filter_list = [filter]

		for f in filter_list:			
			if f.lower() in acction.lower() or f == "*":
				match = True
				
		if reverse:
			return not match
		else:
			return match

	def setAlertToAction(self, pchain, enable):
		
		for process in pchain:
			if process.guid in self.actions_matched:
				for action in self.actions_matched[process.guid]:
					action['Alert'] = enable

	def get_node_by_guid(self, computer, process_guid):
		if self.processes_tree[computer].has_key(process_guid):
			return self.processes_tree[computer][process_guid]
		else:
			return None



class Node_(object):
	def __init__(self, req):

		# pid de sysmon id 1
		self.pid = req['ProcessId']
		
		# command line de sysmon id 1
		self.cmd = req['CommandLine']
	
		# uniq process id
		self.guid = req['ProcessGuid']

		# uniq pprocess id
		self.ParentProcessGuid = req['ParentProcessGuid']

		# process image
		self.ImageFileName = get_image_fileName(req['Image'])
		

		#diccionario donde para cada accion (conexion , modificacion registro..)
		# se guarda un listado de las mismas
		self.acciones = {'1':[],'2':[], '3':[], '5':[],'7':[],
						'8':[],'9':[],'10':[],'11':[],
						'12':[],'13':[],'14':[],'15':[],
						'17':[],'18':[],'22':[],'100':[],'108':[],'110':[]}

		#key ChildProcessGuid
		self.childs = self.acciones['100']

		# BASELINE Engine Attributes
		# baseline process points
		self.points = 100
		
		# baseline result suspicious actions
		self.suspicious_actions = []
		
		# baseline already notified
		self.notified = False

	def __str__(self):
		return "[" + str(self.pid) +"] "  + self.cmd

	def getCreationTime(self):
		try:
			c_time = self.acciones["1"][0]["UtcTime"]
			
			#UtcTime: 2020-01-13 07:51:59.575
			c_time = datetime.datetime.strptime(c_time, '%Y-%m-%d %H:%M:%S.%f') 
		except:
			c_time = False
			
		return c_time
		
	def getTerminationTime(self):
		try:
			t_time = self.acciones["5"][0]["UtcTime"]
			t_time = datetime.datetime.strptime(t_time, '%Y-%m-%d %H:%M:%S.%f')
		except:
			t_time = False
			
		return t_time	
	
	def getLiveTime(self):
		
		c_time = self.getCreationTime()
		t_time = self.getTerminationTime()
		
		if c_time and t_time:
			l_time = t_time - c_time
			return l_time
		else:
			return False


	def update_process_creation_origin(self, req, computer_ptree):
		'''
			Method for detecting if a thread has been created by other process
			(not parent) using remote injection technics. "Realparent" records
			the injector process. We need 3 kinds of event id for detecting 
			real parent: CreateRemoteThread 8 (108), Openprocess 10 and
			processcreate 1 (100). When a process is created (1) normally we'll 
			find an OpenProcess (10) event with the souce thread registered.
			Would be greate to have it at ID 1 Mark!!
		'''
		# let's check if parent process has injected thread first
		if self.acciones['100'] != [] and self.acciones['108'] != [] \
										and req['idEvent'] == 10:
			for action108 in self.acciones['108']:
				if action108["NewThreadId"] == req["ThreadId"]:

					for child in self.acciones['100']:
						node = computer_ptree[child["ChildProcessGuid"]]

						if node.acciones["1"][0]["ProcessGuid"] == \
												req["TargetProcessGuid"]:
						
							parent = "(" + action108["SourceProcessId"] + \
										") " + action108["SourceImage"]
										
							c_origin = {"CreationType":"InjectedThread",\
										"RealParent":parent}
											
							node.acciones["1"][0].update(c_origin)

	'''Baseline related methods
	'''
	def add_suspicious_action(self, s_action):
		for action in s_action:
			self.suspicious_actions.append(action)
	
	def subtract_points(self, s_points):
			self.points -= s_points
	
	def get_suspicious_actions(self):
		return self.suspicious_actions + [{'PointsLeft': self.points}]
		
	def setNotified(self):
		self.notified = True
