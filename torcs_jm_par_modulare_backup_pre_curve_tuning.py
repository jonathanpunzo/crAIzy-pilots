
import socket
import sys
import getopt
import os
import time
import csv
PI= 3.14159265359

data_size = 2**17

ophelp=  'Options:\n'
ophelp+= ' --host, -H <host>    TORCS server host. [localhost]\n'
ophelp+= ' --port, -p <port>    TORCS port. [3001]\n'
ophelp+= ' --id, -i <id>        ID for server. [SCR]\n'
ophelp+= ' --steps, -m <#>      Maximum simulation steps. 1 sec ~ 50 steps. [100000]\n'
ophelp+= ' --episodes, -e <#>   Maximum learning episodes. [1]\n'
ophelp+= ' --track, -t <track>  Your name for this track. Used for learning. [unknown]\n'
ophelp+= ' --stage, -s <#>      0=warm up, 1=qualifying, 2=race, 3=unknown. [3]\n'
ophelp+= ' --debug, -d          Output full telemetry.\n'
ophelp+= ' --help, -h           Show this help.\n'
ophelp+= ' --version, -v        Show current version.'
usage= 'Usage: %s [ophelp [optargs]] \n' % sys.argv[0]
usage= usage + ophelp
version= "20130505-2"

def clip(v,lo,hi):
    if v<lo: return lo
    elif v>hi: return hi
    else: return v

def bargraph(x,mn,mx,w,c='X'):
    '''Draws a simple asciiart bar graph. Very handy for
    visualizing what's going on with the data.
    x= Value from sensor, mn= minimum plottable value,
    mx= maximum plottable value, w= width of plot in chars,
    c= the character to plot with.'''
    if not w: return '' # No width!
    if x<mn: x= mn      # Clip to bounds.
    if x>mx: x= mx      # Clip to bounds.
    tx= mx-mn # Total real units possible to show on graph.
    if tx<=0: return 'backwards' # Stupid bounds.
    upw= tx/float(w) # X Units per output char width.
    if upw<=0: return 'what?' # Don't let this happen.
    negpu, pospu, negnonpu, posnonpu= 0,0,0,0
    if mn < 0: # Then there is a negative part to graph.
        if x < 0: # And the plot is on the negative side.
            negpu= -x + min(0,mx)
            negnonpu= -mn + x
        else: # Plot is on pos. Neg side is empty.
            negnonpu= -mn + min(0,mx) # But still show some empty neg.
    if mx > 0: # There is a positive part to the graph
        if x > 0: # And the plot is on the positive side.
            pospu= x - max(0,mn)
            posnonpu= mx - x
        else: # Plot is on neg. Pos side is empty.
            posnonpu= mx - max(0,mn) # But still show some empty pos.
    nnc= int(negnonpu/upw)*'-'
    npc= int(negpu/upw)*c
    ppc= int(pospu/upw)*c
    pnc= int(posnonpu/upw)*'_'
    return '[%s]' % (nnc+npc+ppc+pnc)

class Client():
    def __init__(self,H=None,p=None,i=None,e=None,t=None,s=None,d=None,vision=False):
        self.vision = vision

        self.host= 'localhost'
        self.port= 3001
        self.sid= 'SCR'
        self.maxEpisodes=1 # "Maximum number of learning episodes to perform"
        self.trackname= 'unknown'
        self.stage= 3 # 0=Warm-up, 1=Qualifying 2=Race, 3=unknown <Default=3>
        self.debug= False
        self.maxSteps= 100000  # 50steps/second
        self.parse_the_command_line()
        if H: self.host= H
        if p: self.port= p
        if i: self.sid= i
        if e: self.maxEpisodes= e
        if t: self.trackname= t
        if s: self.stage= s
        if d: self.debug= d
        self.S= ServerState()
        self.R= DriverAction()
        self.setup_connection()

    def setup_connection(self):
        try:
            self.so= socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except socket.error as emsg:
            print('Error: Could not create socket...')
            sys.exit(-1)
        self.so.settimeout(1)

        n_fail = 5
        while True:
            a= "-45 -19 -12 -7 -4 -2.5 -1.7 -1 -.5 0 .5 1 1.7 2.5 4 7 12 19 45"

            initmsg='%s(init %s)' % (self.sid,a)

            try:
                self.so.sendto(initmsg.encode(), (self.host, self.port))
            except socket.error as emsg:
                sys.exit(-1)
            sockdata= str()
            try:
                sockdata,addr= self.so.recvfrom(data_size)
                sockdata = sockdata.decode('utf-8')
            except socket.error as emsg:
                print("Waiting for server on %d............" % self.port)
                print("Count Down : " + str(n_fail))
                if n_fail < 0:
                    print("relaunch torcs")
                    os.system('pkill torcs')
                    time.sleep(1.0)
                    if self.vision is False:
                        os.system('torcs -nofuel -nodamage -nolaptime &')
                    else:
                        os.system('torcs -nofuel -nodamage -nolaptime -vision &')

                    time.sleep(1.0)
                    os.system('sh autostart.sh')
                    n_fail = 5
                n_fail -= 1

            identify = '***identified***'
            if identify in sockdata:
                print("Client connected on %d.............." % self.port)
                break

    def parse_the_command_line(self):
        try:
            (opts, args) = getopt.getopt(sys.argv[1:], 'H:p:i:m:e:t:s:dhv',
                       ['host=','port=','id=','steps=',
                        'episodes=','track=','stage=',
                        'debug','help','version'])
        except getopt.error as why:
            print('getopt error: %s\n%s' % (why, usage))
            sys.exit(-1)
        try:
            for opt in opts:
                if opt[0] == '-h' or opt[0] == '--help':
                    print(usage)
                    sys.exit(0)
                if opt[0] == '-d' or opt[0] == '--debug':
                    self.debug= True
                if opt[0] == '-H' or opt[0] == '--host':
                    self.host= opt[1]
                if opt[0] == '-i' or opt[0] == '--id':
                    self.sid= opt[1]
                if opt[0] == '-t' or opt[0] == '--track':
                    self.trackname= opt[1]
                if opt[0] == '-s' or opt[0] == '--stage':
                    self.stage= int(opt[1])
                if opt[0] == '-p' or opt[0] == '--port':
                    self.port= int(opt[1])
                if opt[0] == '-e' or opt[0] == '--episodes':
                    self.maxEpisodes= int(opt[1])
                if opt[0] == '-m' or opt[0] == '--steps':
                    self.maxSteps= int(opt[1])
                if opt[0] == '-v' or opt[0] == '--version':
                    print('%s %s' % (sys.argv[0], version))
                    sys.exit(0)
        except ValueError as why:
            print('Bad parameter \'%s\' for option %s: %s\n%s' % (
                                       opt[1], opt[0], why, usage))
            sys.exit(-1)
        if len(args) > 0:
            print('Superflous input? %s\n%s' % (', '.join(args), usage))
            sys.exit(-1)

    def get_servers_input(self):
        '''Server's input is stored in a ServerState object'''
        if not self.so: return
        sockdata= str()

        while True:
            try:
                sockdata,addr= self.so.recvfrom(data_size)
                sockdata = sockdata.decode('utf-8')
            except socket.error as emsg:
                print('.', end=' ')
            if '***identified***' in sockdata:
                print("Client connected on %d.............." % self.port)
                continue
            elif '***shutdown***' in sockdata:
                print((("Server has stopped the race on %d. "+
                        "You were in %d place.") %
                        (self.port,self.S.d['racePos'])))
                self.shutdown()
                return
            elif '***restart***' in sockdata:
                print("Server has restarted the race on %d." % self.port)
                self.shutdown()
                return
            elif not sockdata: # Empty?
                continue       # Try again.
            else:
                self.S.parse_server_str(sockdata)
                if self.debug:
                    sys.stderr.write("\x1b[2J\x1b[H") # Clear for steady output.
                    print(self.S)
                break # Can now return from this function.

    def respond_to_server(self):
        if not self.so: return
        try:
            message = repr(self.R)
            self.so.sendto(message.encode(), (self.host, self.port))
        except socket.error as emsg:
            print("Error sending to server: %s Message %s" % (emsg[1],str(emsg[0])))
            sys.exit(-1)
        if self.debug: print(self.R.fancyout())

    def shutdown(self):
        if not self.so: return
        print(("Race terminated or %d steps elapsed. Shutting down %d."
               % (self.maxSteps,self.port)))
        self.so.close()
        self.so = None

class ServerState():
    '''What the server is reporting right now.'''
    def __init__(self):
        self.servstr= str()
        self.d= dict()

    def parse_server_str(self, server_string):
        '''Parse the server string.'''
        self.servstr= server_string.strip()[:-1]
        sslisted= self.servstr.strip().lstrip('(').rstrip(')').split(')(')
        for i in sslisted:
            w= i.split(' ')
            self.d[w[0]]= destringify(w[1:])

    def __repr__(self):
        return self.fancyout()
        out= str()
        for k in sorted(self.d):
            strout= str(self.d[k])
            if type(self.d[k]) is list:
                strlist= [str(i) for i in self.d[k]]
                strout= ', '.join(strlist)
            out+= "%s: %s\n" % (k,strout)
        return out

    def fancyout(self):
        '''Specialty output for useful ServerState monitoring.'''
        out= str()
        sensors= [ # Select the ones you want in the order you want them.
        'stucktimer',
        'fuel',
        'distRaced',
        'distFromStart',
        'opponents',
        'wheelSpinVel',
        'z',
        'speedZ',
        'speedY',
        'speedX',
        'targetSpeed',
        'rpm',
        'skid',
        'slip',
        'track',
        'trackPos',
        'angle',
        ]

        for k in sensors:
            if type(self.d.get(k)) is list: # Handle list type data.
                if k == 'track': # Nice display for track sensors.
                    strout= str()
                    raw_tsens= ['%.1f'%x for x in self.d['track']]
                    strout+= ' '.join(raw_tsens[:9])+'_'+raw_tsens[9]+'_'+' '.join(raw_tsens[10:])
                elif k == 'opponents': # Nice display for opponent sensors.
                    strout= str()
                    for osensor in self.d['opponents']:
                        if   osensor >190: oc= '_'
                        elif osensor > 90: oc= '.'
                        elif osensor > 39: oc= chr(int(osensor/2)+97-19)
                        elif osensor > 13: oc= chr(int(osensor)+65-13)
                        elif osensor >  3: oc= chr(int(osensor)+48-3)
                        else: oc= '?'
                        strout+= oc
                    strout= ' -> '+strout[:18] + ' ' + strout[18:]+' <-'
                else:
                    strlist= [str(i) for i in self.d[k]]
                    strout= ', '.join(strlist)
            else: # Not a list type of value.
                if k == 'gear': # This is redundant now since it's part of RPM.
                    gs= '_._._._._._._._._'
                    p= int(self.d['gear']) * 2 + 2  # Position
                    l= '%d'%self.d['gear'] # Label
                    if l=='-1': l= 'R'
                    if l=='0':  l= 'N'
                    strout= gs[:p]+ '(%s)'%l + gs[p+3:]
                elif k == 'damage':
                    strout= '%6.0f %s' % (self.d[k], bargraph(self.d[k],0,10000,50,'~'))
                elif k == 'fuel':
                    strout= '%6.0f %s' % (self.d[k], bargraph(self.d[k],0,100,50,'f'))
                elif k == 'speedX':
                    cx= 'X'
                    if self.d[k]<0: cx= 'R'
                    strout= '%6.1f %s' % (self.d[k], bargraph(self.d[k],-30,300,50,cx))
                elif k == 'speedY': # This gets reversed for display to make sense.
                    strout= '%6.1f %s' % (self.d[k], bargraph(self.d[k]*-1,-25,25,50,'Y'))
                elif k == 'speedZ':
                    strout= '%6.1f %s' % (self.d[k], bargraph(self.d[k],-13,13,50,'Z'))
                elif k == 'z':
                    strout= '%6.3f %s' % (self.d[k], bargraph(self.d[k],.3,.5,50,'z'))
                elif k == 'trackPos': # This gets reversed for display to make sense.
                    cx='<'
                    if self.d[k]<0: cx= '>'
                    strout= '%6.3f %s' % (self.d[k], bargraph(self.d[k]*-1,-1,1,50,cx))
                elif k == 'stucktimer':
                    if self.d[k]:
                        strout= '%3d %s' % (self.d[k], bargraph(self.d[k],0,300,50,"'"))
                    else: strout= 'Not stuck!'
                elif k == 'rpm':
                    g= self.d['gear']
                    if g < 0:
                        g= 'R'
                    else:
                        g= '%1d'% g
                    strout= bargraph(self.d[k],0,10000,50,g)
                elif k == 'angle':
                    asyms= [
                          "  !  ", ".|'  ", "./'  ", "_.-  ", ".--  ", "..-  ",
                          "---  ", ".__  ", "-._  ", "'-.  ", "'\\.  ", "'|.  ",
                          "  |  ", "  .|'", "  ./'", "  .-'", "  _.-", "  __.",
                          "  ---", "  --.", "  -._", "  -..", "  '\\.", "  '|."  ]
                    rad= self.d[k]
                    deg= int(rad*180/PI)
                    symno= int(.5+ (rad+PI) / (PI/12) )
                    symno= symno % (len(asyms)-1)
                    strout= '%5.2f %3d (%s)' % (rad,deg,asyms[symno])
                elif k == 'skid': # A sensible interpretation of wheel spin.
                    frontwheelradpersec= self.d['wheelSpinVel'][0]
                    skid= 0
                    if frontwheelradpersec:
                        skid= .5555555555*self.d['speedX']/frontwheelradpersec - .66124
                    strout= bargraph(skid,-.05,.4,50,'*')
                elif k == 'slip': # A sensible interpretation of wheel spin.
                    frontwheelradpersec= self.d['wheelSpinVel'][0]
                    slip= 0
                    if frontwheelradpersec:
                        slip= ((self.d['wheelSpinVel'][2]+self.d['wheelSpinVel'][3]) -
                              (self.d['wheelSpinVel'][0]+self.d['wheelSpinVel'][1]))
                    strout= bargraph(slip,-5,150,50,'@')
                else:
                    strout= str(self.d[k])
            out+= "%s: %s\n" % (k,strout)
        return out

class DriverAction():
    '''What the driver is intending to do (i.e. send to the server).
    Composes something like this for the server:
    (accel 1)(brake 0)(gear 1)(steer 0)(clutch 0)(focus 0)(meta 0) or
    (accel 1)(brake 0)(gear 1)(steer 0)(clutch 0)(focus -90 -45 0 45 90)(meta 0)'''
    def __init__(self):
       self.actionstr= str()
       self.d= { 'accel':0.2,
                   'brake':0,
                  'clutch':0,
                    'gear':1,
                   'steer':0,
                   'focus':[-90,-45,0,45,90],
                    'meta':0
                    }

    def clip_to_limits(self):
        """There pretty much is never a reason to send the server
        something like (steer 9483.323). This comes up all the time
        and it's probably just more sensible to always clip it than to
        worry about when to. The "clip" command is still a snakeoil
        utility function, but it should be used only for non standard
        things or non obvious limits (limit the steering to the left,
        for example). For normal limits, simply don't worry about it."""
        self.d['steer']= clip(self.d['steer'], -1, 1)
        self.d['brake']= clip(self.d['brake'], 0, 1)
        self.d['accel']= clip(self.d['accel'], 0, 1)
        self.d['clutch']= clip(self.d['clutch'], 0, 1)
        if self.d['gear'] not in [-1, 0, 1, 2, 3, 4, 5, 6]:
            self.d['gear']= 0
        if self.d['meta'] not in [0,1]:
            self.d['meta']= 0
        if type(self.d['focus']) is not list or min(self.d['focus'])<-180 or max(self.d['focus'])>180:
            self.d['focus']= 0

    def __repr__(self):
        self.clip_to_limits()
        out= str()
        for k in self.d:
            out+= '('+k+' '
            v= self.d[k]
            if not type(v) is list:
                out+= '%.3f' % v
            else:
                out+= ' '.join([str(x) for x in v])
            out+= ')'
        return out
        return out+'\n'

    def fancyout(self):
        '''Specialty output for useful monitoring of bot's effectors.'''
        out= str()
        od= self.d.copy()
        od.pop('gear','') # Not interesting.
        od.pop('meta','') # Not interesting.
        od.pop('focus','') # Not interesting. Yet.
        for k in sorted(od):
            if k == 'clutch' or k == 'brake' or k == 'accel':
                strout=''
                strout= '%6.3f %s' % (od[k], bargraph(od[k],0,1,50,k[0].upper()))
            elif k == 'steer': # Reverse the graph to make sense.
                strout= '%6.3f %s' % (od[k], bargraph(od[k]*-1,-1,1,50,'S'))
            else:
                strout= str(od[k])
            out+= "%s: %s\n" % (k,strout)
        return out

def destringify(s):
    '''makes a string into a value or a list of strings into a list of
    values (if possible)'''
    if not s: return s
    if type(s) is str:
        try:
            return float(s)
        except ValueError:
            print("Could not find a value in %s" % s)
            return s
    elif type(s) is list:
        if len(s) < 2:
            return destringify(s[0])
        else:
            return [destringify(i) for i in s]



#############################################
# MODULAR DRIVE LOGIC WITH USER PARAMETERS  #
#############################################

# ================= USER CONFIGURABLE PARAMETERS =================
TARGET_SPEED = 160  # Base target speed in km/h.
STRAIGHT_SPEED = 230
FAST_CORNER_SPEED = 175
MEDIUM_CORNER_SPEED = 135
SHARP_CORNER_SPEED = 95
RECOVERY_SPEED = 65

STEER_GAIN_STRAIGHT = 10
STEER_GAIN_CORNER = 20
CENTERING_GAIN_STRAIGHT = 0.06
CENTERING_GAIN_CORNER = 0.14
SENSOR_STEER_GAIN = 0.45

BRAKE_THRESHOLD = 0.45
MAX_BRAKE = 0.45
GEAR_SPEEDS = [0, 55, 95, 135, 175, 215]  # Speed thresholds for gear shifting.
ENABLE_TRACTION_CONTROL = True  # Toggle traction control system.

STRAIGHT_FRONT_DISTANCE = 135
CORNER_FRONT_DISTANCE = 90
SHARP_FRONT_DISTANCE = 45
CORNER_DIFF_THRESHOLD = 28
SHARP_DIFF_THRESHOLD = 70
MAX_TRACK_SENSOR_DISTANCE = 200.0

LATERAL_SPEED_SOFT_LIMIT = 8
LATERAL_SPEED_HARD_LIMIT = 14
SLIP_SOFT_LIMIT = 2
SLIP_HARD_LIMIT = 6
LOG_DIRECTORY = 'logs'
LOG_FILE = os.path.join(LOG_DIRECTORY, 'torcs_modular_runs.csv')

LOG_FIELDS = [
    'timestamp',
    'log_type',
    'reason',
    'track_name',
    'port',
    'lap_number',
    'steps',
    'elapsed_real_s',
    'lap_time',
    'cur_lap_time',
    'last_lap_time',
    'dist_raced',
    'dist_from_start',
    'damage_delta',
    'final_damage',
    'avg_speed',
    'max_speed',
    'min_speed',
    'max_abs_speed_y',
    'max_abs_track_pos',
    'max_abs_steer',
    'max_accel',
    'max_brake',
    'brake_steps',
    'throttle_steps',
    'off_track_steps',
    'straight_steps',
    'corner_steps',
    'sharp_corner_steps',
    'final_front',
    'final_curve_signal',
    'final_gear',
]

# ================= HELPER FUNCTIONS =================
def average(values):
    return sum(values) / len(values)

def get_value(data, key, default=0.0):
    return data[key] if key in data else default

def rounded(value, digits=3):
    return round(float(value), digits)

class DriveLogger():
    def __init__(self, track_name, port):
        self.track_name = track_name
        self.port = port
        self.completed_laps = 0
        self.last_logged_lap_time = 0.0
        self.reset_stats()

    def reset_stats(self):
        self.start_time = time.time()
        self.steps = 0
        self.speed_sum = 0.0
        self.max_speed = 0.0
        self.min_speed = None
        self.max_abs_speed_y = 0.0
        self.max_abs_track_pos = 0.0
        self.max_abs_steer = 0.0
        self.max_accel = 0.0
        self.max_brake = 0.0
        self.brake_steps = 0
        self.throttle_steps = 0
        self.off_track_steps = 0
        self.straight_steps = 0
        self.corner_steps = 0
        self.sharp_corner_steps = 0
        self.start_damage = None
        self.final_state = {}
        self.final_action = {}
        self.final_track_info = {}

    def record(self, S, R, track_info):
        speed = get_value(S, 'speedX')
        speed_y = get_value(S, 'speedY')
        track_pos = get_value(S, 'trackPos')
        steer = get_value(R, 'steer')
        accel = get_value(R, 'accel')
        brake = get_value(R, 'brake')
        damage = get_value(S, 'damage')
        track = get_value(S, 'track', [])

        if self.start_damage is None:
            self.start_damage = damage

        self.steps += 1
        self.speed_sum += speed
        self.max_speed = max(self.max_speed, speed)
        self.min_speed = speed if self.min_speed is None else min(self.min_speed, speed)
        self.max_abs_speed_y = max(self.max_abs_speed_y, abs(speed_y))
        self.max_abs_track_pos = max(self.max_abs_track_pos, abs(track_pos))
        self.max_abs_steer = max(self.max_abs_steer, abs(steer))
        self.max_accel = max(self.max_accel, accel)
        self.max_brake = max(self.max_brake, brake)

        if brake > 0.05:
            self.brake_steps += 1
        if accel > 0.50:
            self.throttle_steps += 1
        if abs(track_pos) > 1.0 or (track and min(track) < 0):
            self.off_track_steps += 1

        if track_info['is_sharp_corner']:
            self.sharp_corner_steps += 1
        elif track_info['is_straight']:
            self.straight_steps += 1
        else:
            self.corner_steps += 1

        self.final_state = S.copy()
        self.final_action = R.copy()
        self.final_track_info = track_info.copy()

    def log_completed_lap_if_needed(self):
        last_lap_time = get_value(self.final_state, 'lastLapTime')

        if last_lap_time <= 0 or last_lap_time == self.last_logged_lap_time:
            return

        self.completed_laps += 1
        self.last_logged_lap_time = last_lap_time
        self.write_row('lap_complete', 'finish_line', last_lap_time)
        self.reset_stats()

    def write_final(self, reason):
        if self.steps == 0:
            return
        if self.completed_laps > 0 and self.steps < 10:
            return

        self.write_row('session_end', reason, '')

    def write_row(self, log_type, reason, lap_time):
        os.makedirs(LOG_DIRECTORY, exist_ok=True)

        final_damage = get_value(self.final_state, 'damage')
        damage_start = self.start_damage if self.start_damage is not None else final_damage
        avg_speed = self.speed_sum / self.steps if self.steps else 0.0
        min_speed = self.min_speed if self.min_speed is not None else 0.0

        row = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'log_type': log_type,
            'reason': reason,
            'track_name': self.track_name,
            'port': self.port,
            'lap_number': self.completed_laps,
            'steps': self.steps,
            'elapsed_real_s': rounded(time.time() - self.start_time),
            'lap_time': lap_time,
            'cur_lap_time': rounded(get_value(self.final_state, 'curLapTime')),
            'last_lap_time': rounded(get_value(self.final_state, 'lastLapTime')),
            'dist_raced': rounded(get_value(self.final_state, 'distRaced')),
            'dist_from_start': rounded(get_value(self.final_state, 'distFromStart')),
            'damage_delta': rounded(final_damage - damage_start),
            'final_damage': rounded(final_damage),
            'avg_speed': rounded(avg_speed),
            'max_speed': rounded(self.max_speed),
            'min_speed': rounded(min_speed),
            'max_abs_speed_y': rounded(self.max_abs_speed_y),
            'max_abs_track_pos': rounded(self.max_abs_track_pos),
            'max_abs_steer': rounded(self.max_abs_steer),
            'max_accel': rounded(self.max_accel),
            'max_brake': rounded(self.max_brake),
            'brake_steps': self.brake_steps,
            'throttle_steps': self.throttle_steps,
            'off_track_steps': self.off_track_steps,
            'straight_steps': self.straight_steps,
            'corner_steps': self.corner_steps,
            'sharp_corner_steps': self.sharp_corner_steps,
            'final_front': rounded(get_value(self.final_track_info, 'front')),
            'final_curve_signal': rounded(get_value(self.final_track_info, 'curve_signal')),
            'final_gear': int(get_value(self.final_state, 'gear')),
        }

        file_exists = os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 0
        with open(LOG_FILE, 'a', newline='') as log_file:
            writer = csv.DictWriter(log_file, fieldnames=LOG_FIELDS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

        print("Telemetry log saved to %s" % LOG_FILE)

def analyze_track(S):
    track = [max(0.0, value) for value in S['track']]
    front = track[9]
    left_front = average(track[6:9])
    right_front = average(track[10:13])
    front_window = average(track[7:12])
    curve_signal = right_front - left_front

    is_straight = front > STRAIGHT_FRONT_DISTANCE and abs(curve_signal) < CORNER_DIFF_THRESHOLD
    is_sharp_corner = front < SHARP_FRONT_DISTANCE or abs(curve_signal) > SHARP_DIFF_THRESHOLD
    is_corner = not is_straight or front < CORNER_FRONT_DISTANCE or abs(curve_signal) > CORNER_DIFF_THRESHOLD

    return {
        'front': front,
        'front_window': front_window,
        'curve_signal': curve_signal,
        'is_straight': is_straight,
        'is_corner': is_corner,
        'is_sharp_corner': is_sharp_corner,
    }

def calculate_target_speed(S, track_info):
    speed = TARGET_SPEED

    if track_info['is_straight']:
        speed = STRAIGHT_SPEED
    elif track_info['is_sharp_corner']:
        speed = SHARP_CORNER_SPEED
    elif track_info['front'] > CORNER_FRONT_DISTANCE:
        speed = FAST_CORNER_SPEED
    else:
        speed = MEDIUM_CORNER_SPEED

    if abs(S['trackPos']) > 0.95:
        speed = min(speed, RECOVERY_SPEED)
    elif abs(S['trackPos']) > 0.65:
        speed = min(speed, MEDIUM_CORNER_SPEED)

    if abs(S['speedY']) > LATERAL_SPEED_HARD_LIMIT:
        speed = min(speed, SHARP_CORNER_SPEED)
    elif abs(S['speedY']) > LATERAL_SPEED_SOFT_LIMIT:
        speed = min(speed, MEDIUM_CORNER_SPEED)

    return speed

def calculate_steering(S, track_info):
    angle = S['angle']
    track_pos = S['trackPos']

    if track_info['is_straight']:
        angle_gain = STEER_GAIN_STRAIGHT
        centering_gain = CENTERING_GAIN_STRAIGHT
        angle_dead_zone = 0.03
        position_dead_zone = 0.05
        sensor_steer = 0.0
    else:
        angle_gain = STEER_GAIN_CORNER
        centering_gain = CENTERING_GAIN_CORNER
        angle_dead_zone = 0.015
        position_dead_zone = 0.03
        sensor_steer = (track_info['curve_signal'] / MAX_TRACK_SENSOR_DISTANCE) * SENSOR_STEER_GAIN

    if abs(angle) < angle_dead_zone:
        angle = 0.0
    if abs(track_pos) < position_dead_zone:
        track_pos = 0.0

    steer = (angle * angle_gain / PI) - (track_pos * centering_gain) + sensor_steer

    if abs(track_pos) > 0.85:
        steer -= track_pos * 0.25

    if S['speedX'] > 190:
        steer *= 0.50
    elif S['speedX'] > 150:
        steer *= 0.65
    elif S['speedX'] > 110:
        steer *= 0.80

    if abs(S['speedY']) > LATERAL_SPEED_SOFT_LIMIT:
        steer *= 0.85

    return clip(steer, -1, 1)

def calculate_throttle(S, R, track_info):
    target_speed = calculate_target_speed(S, track_info)
    steering_penalty = abs(R['steer']) * 35
    lateral_penalty = abs(S['speedY']) * 1.5
    effective_target = target_speed - steering_penalty - lateral_penalty

    if S['speedX'] < 10:
        accel = 1.0
    elif R['brake'] > 0.05:
        accel = 0.0
    elif S['speedX'] < effective_target - 15:
        accel = min(1.0, R['accel'] + 0.25)
    elif S['speedX'] < effective_target:
        accel = min(1.0, R['accel'] + 0.10)
    else:
        accel = max(0.0, R['accel'] - 0.30)

    if track_info['is_sharp_corner'] and S['speedX'] > SHARP_CORNER_SPEED:
        accel = min(accel, 0.15)

    if abs(S['speedY']) > LATERAL_SPEED_HARD_LIMIT:
        accel *= 0.35
    elif abs(S['speedY']) > LATERAL_SPEED_SOFT_LIMIT:
        accel *= 0.65

    return clip(accel, 0, 1)

def apply_brakes(S, track_info):
    target_speed = calculate_target_speed(S, track_info)
    overspeed = S['speedX'] - target_speed
    brake = 0.0

    if overspeed > 45:
        brake = MAX_BRAKE
    elif overspeed > 28:
        brake = 0.35
    elif overspeed > 14:
        brake = 0.18

    if overspeed > 10 and track_info['front'] < S['speedX'] * 0.35:
        brake = max(brake, MAX_BRAKE)
    elif overspeed > 5 and track_info['front'] < S['speedX'] * 0.50:
        brake = max(brake, 0.30)

    if track_info['front_window'] < SHARP_FRONT_DISTANCE and S['speedX'] > SHARP_CORNER_SPEED + 15:
        brake = max(brake, 0.35)

    if abs(S['angle']) > BRAKE_THRESHOLD and S['speedX'] > MEDIUM_CORNER_SPEED:
        brake = max(brake, 0.25)

    if abs(S['speedY']) > LATERAL_SPEED_HARD_LIMIT:
        brake = max(brake, 0.20)

    if abs(S['trackPos']) > 0.95 and S['speedX'] > RECOVERY_SPEED:
        brake = max(brake, 0.30)

    return clip(brake, 0, 1)

def shift_gears(S):
    gear = 1
    for i, speed in enumerate(GEAR_SPEEDS):
        if S['speedX'] > speed:
            gear = i + 1
    return min(gear, 6)

def traction_control(S, accel):
    if ENABLE_TRACTION_CONTROL:
        slip = ((S['wheelSpinVel'][2] + S['wheelSpinVel'][3]) -
                (S['wheelSpinVel'][0] + S['wheelSpinVel'][1]))
        if slip > SLIP_HARD_LIMIT:
            accel -= 0.25
        elif slip > SLIP_SOFT_LIMIT:
            accel -= 0.10

    return clip(accel, 0, 1)

# ================= MAIN DRIVE FUNCTION =================
def drive_modular(c):
    S, R = c.S.d, c.R.d
    track_info = analyze_track(S)

    R['steer'] = calculate_steering(S, track_info)
    R['brake'] = apply_brakes(S, track_info)
    R['accel'] = calculate_throttle(S, R, track_info)
    R['accel'] = traction_control(S, R['accel'])
    R['gear'] = shift_gears(S)
    return track_info

# ================= MAIN LOOP =================
if __name__ == "__main__":
    C = Client(p=3001)
    logger = DriveLogger(C.trackname, C.port)
    stop_reason = 'max_steps'

    try:
        for step in range(C.maxSteps, 0, -1):
            C.get_servers_input()
            if not C.so:
                stop_reason = 'server_closed'
                break

            track_info = drive_modular(C)
            logger.record(C.S.d, C.R.d, track_info)
            logger.log_completed_lap_if_needed()
            C.respond_to_server()
    except KeyboardInterrupt:
        stop_reason = 'keyboard_interrupt'
    finally:
        logger.write_final(stop_reason)
        C.shutdown()
