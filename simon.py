import os
import os.path
import sys
import time
from fnmatch import fnmatch

from daemon import runner

from nbody6 import Nbody6
from simulation_task import SimulationTask

# TODO: move the configuration to a text file called 'SiMon.conf'. Parse the config file with regex.
# sim_dir = '/Users/penny/Works/simon_project/nbody6/Ncode/run'  # Global configurations
sim_dir = '/Users/maxwell/Works/nbody6/Ncode/run'


class SiMon(object):
    """
    Main code of Simulation Monitor (SiMon).
    """
    def __init__(self, pidfile=None, stdin='/dev/tty', stdout='/dev/tty', stderr='/dev/tty',
                 mode='interactive', cwd=sim_dir):
        """
        :param pidfile:
        """
        self.selected_inst = []  # A list of the IDs of selected simulation instances
        # self.id_dict = []  # get the full path by ID
        # self.id_dict_short = []  # get the name of the simulation directory by ID
        self.sim_inst_dict = dict()  # the container of all SimulationTask objects (ID to object mapping)
        self.sim_inst_parent_dict = dict()  # given the current path, find out the instance of the parent
        # self.sim_tree = SimulationTask(0, 'root', cwd, 'STOP')

        # TODO: create subclass instance according to the config file
        self.sim_tree = Nbody6(0, 'root', cwd, 'STOP')
        self.status_dict = None
        self.stdin_path = stdin
        self.stdout_path = stdout
        self.stderr_path = stderr
        self.pidfile_path = pidfile
        self.pidfile_timeout = 5
        self.mode = mode
        self.cwd = cwd
        self.inst_id = 0
        self.tcrit = 100
        self.max_concurrent_jobs = 2
        os.chdir(cwd)

    @staticmethod
    def id_input(prompt):
        """
        Prompt to the user to input the simulation ID (in the interactive mode)
        """
        confirmed = False
        while confirmed is False:
            ids = raw_input(prompt).split(',')
            if raw_input('Your input is \n\t'+str(ids)+', confirm? [Y/N] ').lower() == 'y':
                confirmed = True
                return ids

    def traverse_simulation_dir_tree(self, pattern, base_dir, files):
        """
        Traverse the simulation file structure tree (Breadth-first search), until the leaf (i.e. no restart directory)
        or the simulation is not restartable (directory with the 'STOP' file).
        """
        for filename in sorted(files):
            if fnmatch(filename, pattern):
                if os.path.isdir(os.path.join(base_dir, filename)):
                    fullpath = os.path.join(base_dir, filename)
                    self.inst_id += 1
                    id = self.inst_id

                    # TODO: create subclass instance according to the config file
                    sim_inst = Nbody6(id, filename, fullpath, 'STOP')
                    self.sim_inst_dict[id] = sim_inst
                    sim_inst.id = id
                    sim_inst.fulldir = fullpath
                    sim_inst.name = filename

                    # register the node itself in the parent tree
                    self.sim_inst_parent_dict[fullpath] = sim_inst
                    # register child to the parent
                    sim_inst.parent_id = self.sim_inst_parent_dict[base_dir].id
                    # append the parental node restarting list
                    self.sim_inst_dict[sim_inst.parent_id].restarts.append(sim_inst)
                    # the level of simulation for this node is +1 of its parental simulation
                    sim_inst.level = self.sim_inst_dict[sim_inst.parent_id].level + 1

                    # Get simulation status
                    print fullpath
                    try:
                        sim_inst.mtime = os.stat(os.path.join(fullpath, 'output.log')).st_mtime
                        # sim_inst.t_min, sim_inst.t_max = self.print_sim_status_overview(sim_inst.id)
                        if sim_inst.t_max > sim_inst.t_max_extended:
                            sim_inst.t_max_extended = sim_inst.t_max
                    except OSError:
                        mtime = 'NaN'
                        sim_inst.t_min = 0
                        sim_inst.t_max = 0
                    try:
                        sim_inst.ctime = os.stat(os.path.join(fullpath, 'start_time')).st_ctime
                    except OSError:
                        ctime = 'NaN'
                    try:
                        if os.path.isfile(os.path.join(fullpath, 'process.pid')):
                            fpid = open(os.path.join(fullpath, 'process.pid'),'r')
                            pid = 0
                            pid = int(fpid.readline())
                            try:
                                if pid > 0:
                                    os.kill(pid, 0)
                                    sim_inst.status = 'RUN [%d]' % (pid)
                            except (ValueError, OSError, Exception), e:
                                sim_inst.status = 'STOP'
                            fpid.close()
                        else: # process not running or pid file not exist
                            if time.time()-sim_inst.mtime<120: sim_inst.status = 'RUN'
                            else: sim_inst.status = 'STOP'

                        # TODO: add hung detection to sim_inst.sim_check_status()
                        # if self.check_instance_hanged(id) == True:
                        #     sim_inst.status += ' HANG'

                        if self.tcrit - sim_inst.t_max < 100:
                            sim_inst.status = 'DONE'
                    except Exception:
                        sim_inst.status = 'NaN'

                    # TODO: add error type detection to sim_inst.sim_check_status()
                    # sim_inst.errortype = self.check_instance_error_type(id)
                    self.sim_inst_dict[sim_inst.parent_id].status = sim_inst

                    if sim_inst.t_max_extended > self.sim_inst_dict[sim_inst.parent_id].t_max_extended and \
                            not os.path.isfile(os.path.join(sim_inst.fulldir, 'NORESTART')):
                        # nominate as restart candidate
                        self.sim_inst_dict[sim_inst.parent_id].cid = sim_inst.id
                        self.sim_inst_dict[sim_inst.parent_id].t_max_extended = sim_inst.t_max_extended

    def build_simulation_tree(self):
        """
        Generate the simulation tree data structure, so that a restarted simulation can trace back
        to its ancestor.

        :return: The method has no return. The result is stored in self.sim_tree.
        :type: None
        """
        os.chdir(self.cwd)
        # self.id_dict = dict()
        # self.id_dict_short = dict()
        self.sim_inst_dict = dict()
        # self.sim_inst_parent_dict = dict()
        # self.status_dict = dict()

        # TODO: create subclass instance according to the config file
        self.sim_tree = Nbody6(0, 'root', self.cwd, 'STOP')  # initially only the root node
        self.sim_inst_dict[0] = self.sim_tree  # map ID=0 to the root node
        self.sim_inst_parent_dict[self.cwd.strip()] = self.sim_tree  # map the current dir to be the sim tree root
        # id_list, id_list_short = self.traverse_dir()
        self.inst_id = 0
        # self.status_dict = dict()
        os.path.walk(self.cwd, self.traverse_simulation_dir_tree, '*')
        # Synchronize the status tree
        update_needed = True
        iter = 0
        while update_needed and iter < 30:
            iter += 1
            inst_status_modified = False
            for i in self.sim_inst_dict:
                if i == 0:
                    continue
                inst = self.sim_inst_dict[i]
                if 'RUN' in inst.status or 'DONE' in inst.status:
                    if inst.parent_id > 0 and self.sim_inst_dict[inst.parent_id].status != inst.status:
                        # propagate the status of children (restarted simulation) to parents' status
                        self.sim_inst_dict[inst.parent_id].status = inst.status
                        inst_status_modified = True
            if inst_status_modified is True:
                update_needed = True
            else:
                update_needed = False
        return 0
        # print self.sim_tree

    def print_sim_status_overview(self, sim_id):
        """
        Output an overview of the simulation status in the terminal.

        :return: start and stop time
        :rtype: int
        """
        # self.build_simulation_tree()
        print(self.sim_inst_dict[sim_id])  # print the root node will cause the whole tree to be printed
        return self.sim_inst_dict[sim_id].t_min, self.sim_inst_dict[sim_id].t_max

    @staticmethod
    def print_help():
        print('Usage: python simon.py start|stop|interactive|help')
        print('\tstart: start the daemon')
        print('\tstop: stop the daemon')
        print('\tinteractive: run in interactive mode (no daemon) [default]')
        print('\thelp: print this help message')

    @staticmethod
    def print_task_selector():
        """
        Prompt a menu to allow the user to select a task.

        :return: current selected task symbol.
        """
        opt = ''
        while opt.lower() not in ['l', 's', 'n', 'r', 'c', 'x', 'd', 'k', 'b', 'p', 'q']:
            sys.stdout.write('\n=======================================\n')
            sys.stdout.write('\tList Instances (L), \n\tSelect Instance (S), '
                             '\n\tNew Run (N), \n\tRestart (R), \n\tCheck status (C), '
                             '\n\tExecute (X), \n\tDelete Instance (D), \n\tKill Instance (K), '
                             '\n\tBackup Restart File (B), \n\tPost Processing (P), \n\tQuit (Q): \n')
            opt = raw_input('\nPlease choose an action to continue: ').lower()

        return opt

    def task_handler(self, opt):
        """
        Handles the task selection input from the user (in the interactive mode).

        :param opt: The option from user input.
        """

        if opt == 'q':  # quit interactive mode
            sys.exit(0)
        if opt == 'l':  # list all simulations
            self.build_simulation_tree()
        if opt in ['s', 'n', 'r', 'c', 'x', 'd', 'k', 'b', 'p']:
            if self.mode == 'interactive':
                if self.selected_inst is None or len(self.selected_inst) == 0:
                    self.selected_inst = self.id_input('Please specify a list of IDs: ')
                    sys.stdout.write('Instances ' + str(self.selected_inst) + ' selected.\n')

        # TODO: use message? to rewrite this part in a smarter way
        if opt == 'n':  # start new simulations
            for sid in self.selected_inst:
                if sid in self.sim_inst_dict:
                    self.sim_inst_dict[sid].sim_start()
                else:
                    print('The selected simulation with ID = %d does not exist. Simulation not started.\n' % sid)
        if opt == 'r':  # restart simulations
            for sid in self.selected_inst:
                if sid in self.sim_inst_dict:
                    self.sim_inst_dict[sid].sim_restart()
                else:
                    print('The selected simulation with ID = %d does not exist. Simulation not restarted.\n' % sid)
        if opt == 'c':  # check the recent or current status of the simulation and print it
            for sid in self.selected_inst:
                if sid in self.sim_inst_dict:
                    self.sim_inst_dict[sid].sim_restart()
                else:
                    print('The selected simulation with ID = %d does not exist. Simulation not restarted.\n' % sid)
        if opt == 'x':  # execute an UNIX shell command in the simulation directory
            for sid in self.selected_inst:
                if sid in self.sim_inst_dict:
                    self.sim_inst_dict[sid].sim_shell_exec()
                else:
                    print('The selected simulation with ID = %d does not exist. Cannot execute command.\n' % sid)
        if opt == 'd':  # delete the simulation tree and all its data
            for sid in self.selected_inst:
                if sid in self.sim_inst_dict:
                    self.sim_inst_dict[sid].sim_delete()
                else:
                    print('The selected simulation with ID = %d does not exist. Cannot delete simulation.\n' % sid)
        if opt == 'k':  # kill the UNIX process associate with a simulation task
            for sid in self.selected_inst:
                if sid in self.sim_inst_dict:
                    self.sim_inst_dict[sid].sim_kill()
                else:
                    print('The selected simulation with ID = %d does not exist. Cannot kill simulation.\n' % sid)
        if opt == 'b':  # backup the simulation checkpoint files (for restarting purpose in the future)
            for sid in self.selected_inst:
                if sid in self.sim_inst_dict:
                    self.sim_inst_dict[sid].sim_backup_checkpoint()
                else:
                    print('The selected simulation with ID = %d does not exist. Cannot backup checkpoint.\n' % sid)
        if opt == 'p':  # perform (post)-processing (usually after the simulation is done)
            for sid in self.selected_inst:
                if sid in self.sim_inst_dict:
                    pass
                else:
                    print('The selected simulation with ID = %d does not exist. Cannot perform postprocessing.\n' % sid)

    def auto_scheduler(self):
        """
        The automatic decision maker for the daemon.

        The daemon invokes this method at a fixed period of time. This method checks the
        status of all simulations by traversing to all simulation directories and parsing the
        output files. It subsequently deals with the simulation instance according to the informtion
        gathered.
        """
        os.chdir(self.cwd)
        self.build_simulation_tree()
        schedule_list = []
        concurrent_jobs = 0
        for i in self.sim_inst_dict.keys():
            inst = self.sim_inst_dict[i]
            if 'RUN' in inst.status and inst.cid == -1:
                if os.path.isfile(os.path.join(inst.fulldir, 'process.pid')):
                    try:
                        fpid = open(os.path.join(inst.fulldir, 'process.pid'), 'r')
                        strpid = fpid.readline()
                        fpid.close()
                    except OSError:
                        pass
                    if strpid.strip() in inst.status:
                        try:
                            print 'Stripd = '+strpid
                            os.kill(int(strpid), 0)
                            concurrent_jobs += 1
                        except (OSError, ValueError), e:
                            pass

        print os.path.join(os.getcwd(),'schedule.job')
        if os.path.isfile(os.path.join(os.getcwd(),'schedule.job')):
            sfile = open(os.path.join(os.getcwd(),'schedule.job'))
            try:
                buf = sfile.readline()
                while buf != '':
                    schedule_list.append(buf.strip())
                    buf = sfile.readline()
                sfile.close()
            except Exception:
                sfile.close()
        print 'The following simulations scheudled: '+str(schedule_list)
        for i in self.status_dict.keys():
            if i == 0: # the root group, skip
                continue
            sim = self.sim_inst_dict[i]
            # status = sim.status
            # self.status_dict[i] = status
            # d_name = self.id_dict[i]
            # d_name_short = self.id_dict_short[i]
            print 'Checking instance #%d ==> %s' % (i, d_name)
            if 'RUN' in sim.status:
                if 'HANG' in sim.status:
                    sim.sim_kill()
                    self.build_simulation_tree()
                else:
                    sim.sim_backup_checkpoint()
            elif 'STOP' in sim.status:
                print 'STOP detected: '+sim.fulldir+str(concurrent_jobs)+' '+str(sim.level)
                # TODO: implement t_min, t_max by parsing config file, output file and input infile
                # t_min, t_max = self.print_sim_status_overview()
                t_min = 0
                t_max = 100
                if self.tcrit-t_max <= 100: # mark as finished
                    self.sim_inst_dict[i].status = 'DONE'
                else:
                    if t_max == 0 and sim.name in schedule_list and concurrent_jobs < self.max_concurrent_jobs:
                        # Start new run
                        sim.sim_start()
                        concurrent_jobs += 1

                    elif concurrent_jobs < self.max_concurrent_jobs and sim.level == 1:
                        # search only top level instance to find the restart candidate
                        # build restart path
                        current_inst = self.sim_inst_dict[i]
                        while current_inst.cid != -1:
                            current_inst = self.sim_inst_dict[current_inst.cid]
                        # restart the simulation instance at the leaf node
                        print 'RESTART: #%d ==> %s' % (current_inst.id, current_inst.fulldir)
                        current_inst.sim_restart()
                        concurrent_jobs += 1

    def run(self):
        """
        The entry point of this script if it is run with the daemon.
        """
        os.chdir(self.cwd)
        self.build_simulation_tree()
        while True:
            print('Auto scheduled\n')
            self.auto_scheduler()
            sys.stdout.flush()
            sys.stderr.flush()
            time.sleep(300)

    def interactive_mode(self):
        """
        Run SiMon in the interactive mode. In this mode, the user can see an overview of the simulation status from the
        terminal, and control the simulations accordingly.
        :return:
        """
        os.chdir(self.cwd)
        self.build_simulation_tree()
        self.print_sim_status_overview(0)
        choice = ''
        while choice != 'q':
            choice = SiMon.print_task_selector()
            self.task_handler(choice)

    @staticmethod
    def daemon_mode():
        """
        Run SiMon in the daemon mode.

        In this mode, SiMon will behave as a daemon process. It will scan all simulations periodically, and take measures
        if necessary.
        :return:
        """
        app = SiMon(os.path.join(os.getcwd(), 'run_mgr_daemon.pid'), stdout=os.path.join(os.getcwd(), 'SiMon.out.txt'),
                    stderr=os.path.join(os.getcwd(), 'SiMon.err.txt'), mode='daemon')
        # log system
        logger = logging.getLogger("DaemonLog")
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler = logging.FileHandler("/tmp/SiMon.log")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        # initialize the daemon runner
        daemon_runner = runner.DaemonRunner(app)
        # This ensures that the logger file handle does not get closed during daemonization
        daemon_runner.daemon_context.files_preserve = [handler.stream]
        daemon_runner.do_action()  # fixed time period of calling run()

if __name__ == "__main__":
    # execute only if run as a script
    s = SiMon()
    if len(sys.argv) == 1:
        print('Running SiMon in the interactive mode...')
        s.interactive_mode()
    elif len(sys.argv) > 1:
        if sys.argv[1] in ['start', 'stop']:
            # python daemon will handle these two arguments
            s.daemon_mode()
        elif sys.argv[1] in ['interactive', 'i']:
            s.interactive_mode()
        else:
            s.print_help()
            sys.exit(0)
