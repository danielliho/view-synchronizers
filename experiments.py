## Imports
from subprocess import Popen
import subprocess
from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib
import time
import math
import os
import glob
from datetime import datetime
import argparse
from enum import Enum
import json
import multiprocessing
import random
import shutil
from shutil import copyfile
import re
import mmap
import shlex


#############
## Notes:
## (1) The nodes get started by a MsgStart message, which is currently sent by clients
## (2) The nodes will stop if there is no activity for 'numViews' views,
##     in the sense that no client transactions are processed, only dummy transactions
##     So for performance measurement of the nodes themselves, one can set 'numClTrans'
##     to 1, and nodes will only process dummy transactions
##     TODO: to set it to 0, I have to find a way to stop clients cleanly
## (3) View-changes on timeouts are not implemented yet, currently nodes simply stop when
##     they timeout.
##     TODO: once they are implemented, I have to find a way to stop nodes cleanly
## (4) If 'sleepTime' is too high and 'newViews' too low, then the nodes will give up before
##     they process all the clients' requests because they'll think they've been idle for too
##     long.  Therefore, at the moment for throughput vs. latency measurement, it's better to
##     set 'newViews' to 0, in which case the nodes keep going for ever (until they timeout).
##     The experiments will be stopped after 'cutOffBound' in that case.
####


## Parameters
sgxmode        = "SIM"
#sgxmode       = "HW"
srcsgx         = "source \"${SGX_SDK:-$HOME/opt/intel/sgxsdk}/environment\"" # use SGX_SDK when set, otherwise fall back to the home installation
faults         = [1] #[1,2,4,10] #[1,2,4,10,20,30,40] #[1,2,4,6,8,10,12,14,20,30] # list of numbers of faults
#faults        = [1,10,20,30,40,50]
#faults        = [40]
repeats        = 100 #10 #50 #5 #100 #2     # number of times to repeat each experiment
repeatsL2      = 1
#
numViews       = 30     # number of views in each run
cutOffBound    = 60     # stop experiment after some time
#
numClients     = 1     # number of clients
numNonChCls    = 1     # number of clients for the non-chained versions
numChCls       = 1     # number of clients for the chained versions
numClTrans     = 1     # number of transactions sent by each clients
sleepTime      = 0     # time clients sleep between 2 sends (in microseconds)
timeout        = 5     # timeout before changing changing leader (in seconds)
timeoutMul     = 1     # factor used to multiply the timeout with when timing out
timeoutDiv     = 1     # factor used to divide the timeout with when making progress
#
syncPeriod     = 0     # constrains the number of views between 2 synchronization (rollback-resilient protocol)
joinPeriod     = 0     # constrains the number of sessions between 2 joins (rollback-resilient protocol)
numJoiners     = 0     # number of nodes to join per session (rollback-resilient protocol)
joining        = False # nodes are not joining by default - this is set to true when running experiments based on the number of joining nodes  (rollback-resilient protocol)
#
opdist         = 0
#
numTrans       = 400    # number of transactions
payloadSize    = 0 #256 #0 #256 #128      # total size of a transaction
useMultiCores  = True
numMakeCores   = multiprocessing.cpu_count()  # number of cores to use to make
#
runBase      = False #True
runCheap     = False #True
runQuick     = False #True
runComb      = False #True
runDamr      = False #True
runDama      = False #True
runDamp      = False #True
runDamq      = False #True
runFree      = False #True
runRoll      = False #True
runOnep      = False #True
runOnepB     = False #True
runOnepC     = False #True
runOnepD     = False #True
runChBase    = False #True
runChComb    = False #True
# Debug versions
runQuickDbg  = False #True
runChCombDbg = False #True
#
plotView     = True   # to plot the numbers of handling messages + network
plotHandle   = False  # to plot the numbers of just handling messages, without the network
plotCrypto   = False  # to plot the numbers of do crypto
debugPlot    = True #False  # to print debug info when plotting
showTitle    = True   # to print the title of the figure
plotThroughput = True
plotLatency    = True
expmode      = "" # "TVL"
showLegend1  = True
showLegend2  = False
plotBasic    = True
plotChained  = True
displayPlot  = True # to display a plot once it is generated
showYlabel   = True
displayApp   = "eog"
logScale     = False

plotComb     = True

barPlot      = False #True

# to recompile the code
recompile = True

# To set some plotting parameters for specific experiments
whichExp = ""

# For some experiments we start with f nodes dead
deadNodes    = False #True
numDeadNodesCfg = 0
# if deadNodes then we go with less views and give ourselves more time
if deadNodes:
    numViews = numViews // timeout
    cutOffBound = cutOffBound * 2

# For some experiments we remove the outliers
quantileSize = 20 # Used in Python
quantileSize1 = 0 # Used by the C++ code
quantileSize2 = 0 # Used by the C++ code
skipViews     = 0 # Used by the C++ code -- number of views to skip at the beginning of a run

# don't change, those are hard coded in the C++ code:
statsdir     = "stats"        # stats directory (don't change, hard coded in C++)
params       = "App/params.h" # (don't change, hard coded in C++)
config       = "App/config.h" # (don't change, hard coded in C++)
addresses    = "config"       # (don't change, hard coded in C++)
ipsOfNodes   = {}             # dictionnary mapping node ids to IPs

# to copy all files to AWS instances
copyAll = True
# set to True to randomize regions before assiging nodes to them (especially for low number of nodes)
randomizeRegions = False #True

## Global variables
completeRuns  = 0     # number of runs that successfully completed
abortedRuns   = 0     # number of runs that got aborted
aborted       = []    # list of aborted runs
allLocalPorts = []    # list of all port numbers used in local experiments

dateTimeObj  = datetime.now()
timestampStr = dateTimeObj.strftime("%d-%b-%Y-%H:%M:%S.%f")
pointsFile   = statsdir + "/points-" + timestampStr
timesFile    = statsdir + "/view-times-" + timestampStr
abortedFile  = statsdir + "/aborted-" + timestampStr
plotFile     = statsdir + "/plot-" + timestampStr + ".svg"
clientsFile  = statsdir + "/clients-" + timestampStr
tvlFile      = statsdir + "/tvl-" + timestampStr + ".svg"
debugFile    = statsdir + "/debug-" + timestampStr

# Names
baseHS   = "Basic HotStuff"
cheapHS  = "Damysus-C"
quickHS  = "Damysus-A"
combHS   = "Basic-Damysus"
freeHS   = "Light-Damysus"
damrHS   = "Basic-Damysus+ROTE"  # based on the "free/light" version
damaHS   = "Achilles"            # based on the "free/light" version
dampHS   = "Basic-Damysus"       # Damysus + Pacemaker # based on the "free/light" version
damqHS   = "Flexi-Basic-Damysus" # "Basic-Damysus+Pacemaker+(3f+1)nodes" # based on the "free/light" version
rollHS   = "Pallas"
onepHS   = "Basic-OneShot"
onepbHS  = "Basic-OneShot(2)"
onepcHS  = "Basic-OneShot(3)"
onepdHS  = "Basic-OneShot(4)"
baseChHS = "Chained HotStuff"
combChHS = "Chained-Damysus"

# Markers
baseMRK   = "P"
cheapMRK  = "o"
quickMRK  = "*"
combMRK   = "X"
freeMRK   = "s"
damrMRK   = "p"
damaMRK   = "+"
dampMRK   = "s"
damqMRK   = "*"
rollMRK   = "o"
onepMRK   = "+"
onepbMRK  = "+"
onepcMRK  = "+"
onepdMRK  = "+"
baseChMRK = "d"
combChMRK = ">"

# Line styles
baseLS   = ":"
cheapLS  = "--"
quickLS  = "-."
combLS   = "-"
freeLS   = "-"
damrLS   = ":"
damaLS   = "-"
dampLS   = "-"
damqLS   = "-."
rollLS   = "--"
onepLS   = "-"
onepbLS  = "-"
onepcLS  = "-"
onepdLS  = "-"
baseChLS = ":"
combChLS = "-"

# Markers
baseCOL   = "black"
cheapCOL  = "blue"
quickCOL  = "green"
combCOL   = "red"
freeCOL   = "magenta"
damrCOL   = "black"
damaCOL   = "cyan"
dampCOL   = "purple"
damqCOL   = "green"
rollCOL   = "blue"
onepCOL   = "brown"
onepbCOL  = "pink"
onepcCOL  = "cyan"
onepdCOL  = "yellow"
baseChCOL = "darkorange"
combChCOL = "magenta"


## AWS parameters
instType = "t2.micro"
pem      = "aws.pem"

# Region - North Virginia (us-east-1)
region_USEAST1      = "us-east-1"
imageID_USEAST1     = "ami-03f63e98cb2f222d1"
secGroup_USEAST1    = "sg-056a18930b3b73e9f"

# Region - Ohio (us-east-2)
region_USEAST2      = "us-east-2"
imageID_USEAST2     = "ami-02aae622a1bef20a2"
secGroup_USEAST2    = "sg-0aec5469d109ddaf5"
subnetID_USEAST2_1  = "subnet-bc5baad7" # us-east-2a
subnetID_USEAST2_2  = "subnet-30624c4a" # us-east-2b
subnetID_USEAST2_3  = "subnet-25891f69" # us-east-2c

# Region - North California (us-west-1)
region_USWEST1      = "us-west-1"
imageID_USWEST1     = "ami-0131aae503c1738b7"
secGroup_USWEST1    = "sg-0bbdc16a3f162f685"

# Region - Oregon (us-west-2)
region_USWEST2      = "us-west-2"
imageID_USWEST2     = "ami-0c62776e995e5644e"
secGroup_USWEST2    = "sg-0e7f3ef81efe71201"

# Region - Singapore (ap-southeast-1)
region_APSEAST1     = "ap-southeast-1"
imageID_APSEAST1    = "ami-0921318cc6b996226" #"ami-07a6e7819f6d63dfe" #"ami-087f6cdc8a0780f6f"
secGroup_APSEAST1   = "sg-0a90db70b5ac267f2" #"sg-01de5d6a5bd5576b8"

# Region - Sydney (ap-southeast-2)
region_APSEAST2     = "ap-southeast-2"
imageID_APSEAST2    = "ami-0e0038e3a1e604f34" #"ami-066ec398d3ccac032" #"ami-085ea5cb0e80ebfd1"
secGroup_APSEAST2   = "sg-0c0e848464d8a2c41" #"sg-02b6c7b19d8c78ce6"

# Region - Ireland (eu-west-1)
region_EUWEST1      = "eu-west-1"
imageID_EUWEST1     = "ami-0eaa1be7c700b6860"
secGroup_EUWEST1    = "sg-0c9c836572fff794b"

# Region - London (eu-west-2)
region_EUWEST2      = "eu-west-2"
imageID_EUWEST2     = "ami-09d1cc01b57b9f734"
secGroup_EUWEST2    = "sg-04c12388070c59b4f"

# Region - Paris (eu-west-3)
region_EUWEST3      = "eu-west-3"
imageID_EUWEST3     = "ami-091fc9882697f31f2"
secGroup_EUWEST3    = "sg-06d5f2a8f5e86d8ff"

# Region - Frankfurt (eu-central-1)
region_EUCENT1      = "eu-central-1"
imageID_EUCENT1     = "ami-0511cdd436c6b8076"
secGroup_EUCENT1    = "sg-0cc81ab8f10d5016d"

# Region - Canada Central (ca-central-1)
region_CACENT1      = "ca-central-1"
imageID_CACENT1     = "ami-0afc1d0187db50762" #"ami-059fd80230a4c4512" #"ami-006e2b38fa3f30a8e"
secGroup_CACENT1    = "sg-0daa11ad7e1542a37" #"sg-0ce99bc9e1b8a252c"

# Regions around the world
WregionsNAME = "w"
Wregions = [(region_USEAST2,  imageID_USEAST2,  secGroup_USEAST2),
            (region_APSEAST2, imageID_APSEAST2, secGroup_APSEAST2),
            (region_EUWEST2,  imageID_EUWEST2,  secGroup_EUWEST2),
            (region_CACENT1,  imageID_CACENT1,  secGroup_CACENT1)]

# US regions
USregionsNAME = "us"
USregions = [(region_USEAST1, imageID_USEAST1, secGroup_USEAST1),
             (region_USEAST2, imageID_USEAST2, secGroup_USEAST2),
             (region_USWEST1, imageID_USWEST1, secGroup_USWEST1),
             (region_USWEST2, imageID_USWEST2, secGroup_USWEST2)]

# EU regions
EUregionsNAME = "eu"
EUregions = [(region_EUWEST1, imageID_EUWEST1, secGroup_EUWEST1),
             (region_EUWEST2, imageID_EUWEST2, secGroup_EUWEST2),
             (region_EUWEST3, imageID_EUWEST3, secGroup_EUWEST3),
             (region_EUCENT1, imageID_EUCENT1, secGroup_EUCENT1)]
# One region
ONEregionsNAME = "one"
ONEregions = [(region_USEAST2, imageID_USEAST2, secGroup_USEAST2)]

# All regions
ALLregionsNAME = "all"
ALLregions = [(region_USEAST1,  imageID_USEAST1,  secGroup_USEAST1),
              (region_USEAST2,  imageID_USEAST2,  secGroup_USEAST2),
              (region_USWEST1,  imageID_USWEST1,  secGroup_USWEST1),
              (region_USWEST2,  imageID_USWEST2,  secGroup_USWEST2),
              (region_EUWEST1,  imageID_EUWEST1,  secGroup_EUWEST1),
              (region_EUWEST2,  imageID_EUWEST2,  secGroup_EUWEST2),
              (region_EUWEST3,  imageID_EUWEST3,  secGroup_EUWEST3),
              (region_EUCENT1,  imageID_EUCENT1,  secGroup_EUCENT1),
              (region_APSEAST1, imageID_APSEAST1, secGroup_APSEAST1),
              (region_APSEAST2, imageID_APSEAST2, secGroup_APSEAST2),
              (region_CACENT1,  imageID_CACENT1,  secGroup_CACENT1)]

# All regions -- same as ALLregions but in a different order
ALL2regionsNAME = "all2"
ALL2regions = [(region_USEAST1,  imageID_USEAST1,  secGroup_USEAST1),
               (region_EUWEST1,  imageID_EUWEST1,  secGroup_EUWEST1),
               (region_APSEAST1, imageID_APSEAST1, secGroup_APSEAST1),
               (region_CACENT1,  imageID_CACENT1,  secGroup_CACENT1),
               (region_USEAST2,  imageID_USEAST2,  secGroup_USEAST2),
               (region_EUWEST2,  imageID_EUWEST2,  secGroup_EUWEST2),
               (region_APSEAST2, imageID_APSEAST2, secGroup_APSEAST2),
               (region_USWEST1,  imageID_USWEST1,  secGroup_USWEST1),
               (region_EUWEST3,  imageID_EUWEST3,  secGroup_EUWEST3),
               (region_USWEST2,  imageID_USWEST2,  secGroup_USWEST2),
               (region_EUCENT1,  imageID_EUCENT1,  secGroup_EUCENT1)]

# EU/UK regions
ALL3regionsNAME = "all3"
ALL3regions = [(region_USEAST1,  imageID_USEAST1,  secGroup_USEAST1),
               (region_EUWEST1,  imageID_EUWEST1,  secGroup_EUWEST1),
               (region_USEAST2,  imageID_USEAST2,  secGroup_USEAST2),
               (region_EUWEST2,  imageID_EUWEST2,  secGroup_EUWEST2),
               (region_USWEST1,  imageID_USWEST1,  secGroup_USWEST1),
               (region_EUWEST3,  imageID_EUWEST3,  secGroup_EUWEST3),
               (region_USWEST2,  imageID_USWEST2,  secGroup_USWEST2),
               (region_EUCENT1,  imageID_EUCENT1,  secGroup_EUCENT1)]

## regions = (USregionsNAME, USregions)
#regions = (EUregionsNAME, EUregions)
## regions = (WregionsNAME, Wregions)
regions = (ONEregionsNAME, ONEregions)
#regions = (ALLregionsNAME, ALLregions)
## regions = (ALL2regionsNAME, ALL2regions)


sshOpt1  = "StrictHostKeyChecking=no"
sshOpt2  = "ConnectTimeout=10"
sshOpt3  = "ServerAliveInterval=60"
sshOpt4  = "TCPKeepAlive=yes"
sshOpt5  = "serverAliveCountMax=20"


# Files
instFile  = "instances"
descrFile = "description"


## Docker parameters

runDocker  = False      # to run the code within docker contrainers
docker     = "docker"
dockerBase = "damysus2"  # name of the docker container
networkLat = 0          # network latency in ms
networkVar = 0          # variation of the network latency
rateMbit   = 0          # bandwidth
dockerMem  = 0          # memory used by containers (0 means no constraints)
dockerCpu  = 0          # cpus used by containers (0 means no constraints)
msgLoss    = 0          # % of messages lost
stressNg   = False      # whether to use stress-ng or not

startRport = 8760
startCport = 9760

## Cluster parameters

clusterFile = "nodes"
clusterNet  = "damysusNet" # "bridge"
mybridge    = "damysusNet" # "bridge"

## DAS-5/SLURM parameters

runDas5        = False
das5Nodes      = []          # hostnames allocated by SLURM
das5AddressCmd = "hostname -f"


## Code

class Protocol(Enum):
    BASE      = "BASIC_BASELINE"           # basic baseline
    CHEAP     = "BASIC_CHEAP"              # Checker only
    QUICK     = "BASIC_QUICK"              # Accumulator only
    COMB      = "BASIC_CHEAP_AND_QUICK"    # Damysus (Checker + Accumulator)
    FREE      = "BASIC_FREE"               # hash & signature-free Damysus
    DAMR      = "BASIC_DAMYSUS_ROTE"       # Damysus + kinda ROTE
    DAMA      = "BASIC_DAMYSUS_ACHILLES"   # Damysus + Pacemaker + kinda Achilles
    DAMP      = "BASIC_DAMYSUS_PACEMAKER"  # Damysus + Pacemaker
    DAMQ      = "BASIC_DAMYSUS3_PACEMAKER" # Damysus + Pacemaker + 3f+1 nodes
    ROLL      = "BASIC_ROLL"               # rollback prevention
    ONEP      = "BASIC_ONEP"               # 1+1/2 phase Damysus (case 1)
    ONEPB     = "BASIC_ONEPB"              # 1+1/2 phase Damysus (case 2)
    ONEPC     = "BASIC_ONEPC"              # 1+1/2 phase Damysus (case 3)
    ONEPD     = "BASIC_ONEPD"              # 1+1/2 phase Damysus (case 4)
    CHBASE    = "CHAINED_BASELINE"         # chained baseline
    CHCOMB    = "CHAINED_CHEAP_AND_QUICK"  # chained Damysus
    ## Debug versions
    QUICKDBG  = "BASIC_QUICK_DEBUG"
    CHCOMBDBG = "CHAINED_CHEAP_AND_QUICK_DEBUG" # chained Damysus - debug version


## generates a local config file
def genLocalConf(n,filename):
    open(filename, 'w').close()
    host = "127.0.0.1"

    global allLocalPorts

    print("ips:" , ipsOfNodes)

    f = open(filename,'a')
    for i in range(n):
        host  = ipsOfNodes.get(i,host)
        rport = startRport+i
        cport = startCport+i
        allLocalPorts.append(rport)
        allLocalPorts.append(cport)
        f.write("id:"+str(i)+" host:"+host+" port:"+str(rport)+" port:"+str(cport)+"\n")
    f.close()
# End of genLocalConf


def slurmAvailable():
    return "SLURM_JOB_ID" in os.environ
# End of slurmAvailable


def shellJoin(args):
    return " ".join(map(shlex.quote,args))
# End of shellJoin


def readDas5Nodes():
    if len(das5Nodes) > 0:
        return das5Nodes

    nodelist = os.environ.get("SLURM_NODELIST") or os.environ.get("SLURM_JOB_NODELIST")
    if not nodelist:
        raise RuntimeError("--das5 must run inside a SLURM allocation; SLURM_NODELIST is not set")

    try:
        result = subprocess.run(["scontrol", "show", "hostnames", nodelist],
                                check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True)
        nodes = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        nodes = [line.strip() for line in nodelist.splitlines() if line.strip()]

    if len(nodes) == 0:
        raise RuntimeError("could not determine DAS-5 nodes from SLURM_NODELIST=" + nodelist)

    das5Nodes.extend(nodes)
    print("DAS-5 nodes:", das5Nodes)
    return das5Nodes
# End of readDas5Nodes


def runOnDas5Node(host, cmd, capture=False):
    srun = ["srun", "--overlap", "-N", "1", "-n", "1", "-w", host, "--chdir", os.getcwd(),
            "bash", "-lc", cmd]
    print("the commandline is {}".format(shellJoin(srun)))
    if capture:
        return subprocess.run(srun, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)
    return Popen(srun)
# End of runOnDas5Node


def getDas5Address(host):
    try:
        result = runOnDas5Node(host, das5AddressCmd, capture=True)
        address = result.stdout.strip().splitlines()[-1].strip()
    except (subprocess.CalledProcessError, IndexError):
        address = ""

    if not address:
        address = host

    return address
# End of getDas5Address


def startDas5Processes(numReps,numClients):
    print("running in DAS-5 mode, using SLURM nodes for", numReps, "replicas and", numClients, "clients")

    nodes = readDas5Nodes()
    needed = numReps + numClients
    if len(nodes) < needed:
        print("WARNING: DAS-5 allocation has", len(nodes), "node(s), but this run wants", needed,
              "processes; some nodes will host more than one process")

    global ipsOfNodes
    ipsOfNodes = {}
    for i in range(numReps):
        host = nodes[i % len(nodes)]
        ipsOfNodes.update({i:getDas5Address(host)})

    genLocalConf(numReps,addresses)

    instanceRepIds = []
    instanceClIds  = []
    for i in range(numReps):
        instanceRepIds.append((i, nodes[i % len(nodes)]))
    for i in range(numClients):
        instanceClIds.append((i, nodes[(numReps + i) % len(nodes)]))

    return (instanceRepIds, instanceClIds)
# End of startDas5Processes


def findPublicDnsName(j):
    for res in j["Reservations"]:
        for inst in res["Instances"]:
            priv   = inst["PrivateIpAddress"]
            pub    = inst["PublicIpAddress"]
            dns    = inst["PublicDnsName"]
            status = inst["State"]["Name"]
            if status == "running":
                return (priv,pub,dns)
            else:
                RuntimeError('instance is not yet running')
    raise RuntimeError('Failed to find public dns name')


def getPublicDnsName(region,i):
    while True:
        try:
            g = open(descrFile,'w')
            subprocess.run(["aws","ec2","describe-instances","--region",region,"--instance-ids",i], stdout=g)
            g.close()

            g = open(descrFile,'r')
            output = json.load(g)
            #print(output)
            g.close()

            (priv,pub,dns) = findPublicDnsName(output)
            return (priv,pub,dns)

            # g = open(descrFile,'w')
            # subprocess.run(["aws","ssm","get-connection-status","--target",i], stdout=g)
            # g.close()

            # g = open(descrFile,'r')
            # output = json.load(g)
            # g.close()

            # if output["Status"] == "connected":
            #     return (priv,pub,dns)
            # else:
            #     print("oops, not yet connected:", i)
        except KeyError:
            print("oops, cannot get address yet:", i)
            time.sleep(1)
        except RuntimeError as e:
            print("oops, error:", i, e.args)
            time.sleep(1)



def startInstances(numRepInstances,numClInstances):
    print(">> starting",str(numRepInstances),"replica instance(s)")
    print(">> starting",str(numClInstances),"client instance(s)")

    regs = regions[1]
    if randomizeRegions:
        random.shuffle(regs)

    numInstances = numRepInstances + numClInstances
    numRegions = min(numInstances,len(regs))
    k, r = divmod(numInstances,numRegions)
    #print(str(numInstances),str(numRegions),str(k),str(r))
    allInstances = []

    print("all regions:", str(regs[0:numRegions]))
    for i in range(numRegions):
        iFile = instFile + str(i)

        f = open(iFile,'w')
        reg = regs[i]
        (region,imageID,secGroup) = reg
        count = k+1 if i >= numRegions - r else k # the last r regions all run 1 more instance
        print("starting", str(count), "instance(s) here:", str(reg))
        #subprocess.run(["aws","ec2","run-instances","--region",region,"--image-id",imageID,"--count",str(numRepInstances+numClInstances),"--instance-type",instType,"--security-group-ids",secGroup,"--subnet-id",subnetID1_1], stdout=f)
        #subprocess.run(["aws","ec2","run-instances","--region",region,"--image-id",imageID,"--count",str(numRepInstances+numClInstances),"--instance-type",instType,"--security-group-ids",secGroup], stdout=f)
        print("aws ec2 run-instances --region " + region + " --image-id " + imageID + " --count " + str(count) + " --instance-type " + instType + " --key-name " + "aws" + " --security-group-ids " + secGroup)
        subprocess.run(["aws","ec2","run-instances","--region",region,"--image-id",imageID,"--count",str(count),"--instance-type",instType,"--key-name","aws","--security-group-ids",secGroup], stdout=f)
        f.close()

        f = open(iFile,'r')
        instances = json.load(f)
        allInstances.append((region,instances))
        f.close()

    # we erase the content of the file
    open(addresses,'w').close()

    # List of quadruples generated when lauching AWS EC2 instances:
    #   id/private ip/public ip/public dns
    instanceRepIds = []
    instanceClIds  = []

    n = 0 # total number of instances
    r = 0 # number of replicas
    c = 0 # number of clients
    for (region,instances) in allInstances:
        for inst in instances["Instances"]:
            id = inst["InstanceId"]
            (priv,pub,dns) = getPublicDnsName(region,id)
            print("public dns name:",dns)
            if n < numRepInstances:
                instanceRepIds.append((r,id,priv,pub,dns,region))
                h = open(addresses,'a')
                rport = startRport+r
                cport = startCport+r
                #h.write("id:"+str(r)+" host:"+str(priv)+" port:"+str(rport)+" port:"+str(cport)+"\n")
                h.write("id:"+str(r)+" host:"+str(pub)+" port:"+str(rport)+" port:"+str(cport)+"\n")
                h.close()
                r += 1
            else:
                instanceClIds.append((c,id,priv,pub,dns,region))
                c += 1

            n += 1

    if not(n == (numRepInstances + numClInstances)):
        raise RuntimeError("incorrect number of instances started", n)

    return (instanceRepIds, instanceClIds)
# End of startInstances


def copyToAddr(sshAdr):
    s1  = "scp -i " + pem + " -o " + sshOpt1 + " -o " + sshOpt3 + " -o " + sshOpt4 + " -o " + sshOpt5 + " "
    s2  = " " + sshAdr+":/home/ubuntu/app/"
    scp = "until " + s1 + addresses + s2 + "; do sleep 1; done"
    subprocess.run(scp, shell=True, check=True)
    if copyAll:
        subprocess.run("tar cvzf App.tar.gz --exclude='*.o' App",          shell=True, check=True)
        subprocess.run("tar cvzf Enclave.tar.gz --exclude='*.o' Enclave",  shell=True, check=True)
        subprocess.run(s1 + "Makefile"         + s2 + "",  shell=True, check=True)
        subprocess.run(s1 + "App.tar.gz"       + s2 + "",  shell=True, check=True)
        subprocess.run(s1 + "Enclave.tar.gz"   + s2 + "",  shell=True, check=True)
        cmd = "\"\"cd app && tar xvzf App.tar.gz && tar xvzf Enclave.tar.gz\"\"" # && make clean
        p = Popen(["ssh","-i",pem,"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,cmd])
        p.communicate()
    else:
        subprocess.run(["scp","-i",pem,"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,params,sshAdr+":/home/ubuntu/app/App/"])


def copyToInstances(instances):
    procs = []
    for (n,i,priv,pub,dns,region) in instances:
        sshAdr = "ubuntu@" + dns
        p = multiprocessing.Process(target=copyToAddr(sshAdr))
        p.start()
        procs.append(p)
    for p in procs:
        p.join()
# End of copyToInstances


def makeInstances(instanceIds,protocol):
    ncores = 1
    if useMultiCores:
        ncores = numMakeCores
    print(">> making",str(len(instanceIds)),"instance(s) using",str(ncores),"core(s)")

    make0  = "make -j "+str(ncores)
    make   = make0 + " SGX_MODE="+sgxmode if needsSGX(protocol) else make0 + " server client"

    # copying
    procs = []
    for (n,i,priv,pub,dns,region) in instanceIds:
        sshAdr = "ubuntu@" + dns
        p      = Popen(["scp","-i",pem,"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,params,sshAdr+":/home/ubuntu/app/App/"])
        procs.append(("R",n,i,priv,pub,dns,region,p))
        print("COPYNIG:",i)

    for (tag,n,i,priv,pub,dns,region,p) in procs:
        while (p.poll() is None):
            time.sleep(1)
        print("copy done:",i)

    # then making - we reset procs
    procs = []
    for (n,i,priv,pub,dns,region) in instanceIds:
        sshAdr  = "ubuntu@" + dns
        #subprocess.run(["scp","-i",pem,"-o",sshOpt1,params,sshAdr+":/home/ubuntu/app/App/"])
        #copyToAddr(sshAdr)

        stressCmd = "pwd"
        if stressNg:
            print("installing stress-ng")
            stressCmd = "sudo add-apt-repository -y ppa:colin-king/stress-ng && sudo apt update && sudo apt install -y stress-ng"

        lossCmd = "pwd"
        if msgLoss > 0:
            print("setting message loss:", msgLoss)
            lossCmd = "sudo tc qdisc add dev eth0 root netem loss " + str(msgLoss) + "%"
        cmd     = "\"\"" + srcsgx + " && cd app && mkdir -p stats && make clean && " + make + " && " + stressCmd + " && " + lossCmd + "\"\""
        p       = Popen(["ssh","-i",pem,"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,cmd])
        print("MAKING:",i)
        print("the commandline is {}".format(p.args))
        procs.append(("R",n,i,priv,pub,dns,region,p))

    for (tag,n,i,priv,pub,dns,region,p) in procs:
        while (p.poll() is None):
            time.sleep(1)
        print("process done:",i)

    print("all instances are made")
# End of makeInstances


def copyClientStats(instanceClIds):
    for (n,i,priv,pub,dns,region) in instanceClIds:
        sshAdr = "ubuntu@" + dns
        subprocess.run(["scp","-i",pem,"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,sshAdr+":/home/ubuntu/app/stats/*","stats/"])
# End of copyClientStats


def executeInstances(instanceRepIds,instanceClIds,protocol,constFactor,numClTrans,sleepTime,numViews,cutOffBound,numFaults,numJoiners,instance):
    newtimeout = timeout #int(math.ceil(timeout+math.log(numFaults,2)))
    print(">> timeout change: ", str(timeout), " -> " , str (newtimeout))

    print(">> connecting to",str(len(instanceRepIds)),"replica instance(s)")
    print(">> connecting to",str(len(instanceClIds)),"client instance(s)")

    procsRep   = []
    procsCl    = []
    server     = "./sgxserver" if needsSGX(protocol) else "./server"
    client     = "./sgxclient" if needsSGX(protocol) else "./client"

    stressCmd = "pwd"
    if stressNg:
        print("starting stress-ng")
        stressCmd = "stress-ng --cpu 1 --timeout 60s"

    for (n,i,priv,pub,dns,region) in instanceRepIds:
        # we give some time for the nodes to connect gradually
        if (n%10 == 5):
            time.sleep(2)
        sshAdr = "ubuntu@" + dns
        srun2  = server + " " + str(n) + " " + str(numFaults) + " " + str(constFactor) + " " + str(numViews) + " " + str(newtimeout) + " " + str(timeoutMul) + " " + str(timeoutDiv) + " " + str(opdist) + " " + str(syncPeriod) + " " + str(joinPeriod) + " " + str(numJoiners) + " " + str(quantileSize1) + " " + str(quantileSize2) + " " + str(skipViews)
        srun   = "screen -d -m " + srun2
        cmd    = "\"\"" + srcsgx + " && cd app && rm -f stats/* && " + stressCmd + " && " + srun2 + "\"\""
        p      = Popen(["ssh","-i",pem,"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,cmd])
        print("the commandline is {}".format(p.args))
        procsRep.append(("R",n,i,priv,pub,dns,region,p))

    print("starting", len(procsRep), "replicas")

    totalStartTime = 0

    remaining = procsRep.copy()
    while 0 < len(remaining) and totalStartTime < cutOffBound:
        print("processes that haven't started (" , totalStartTime , "," , cutOffBound , "):", remaining)
        totalStartTime += 1
        rem = remaining.copy()
        for (tag,n,i,priv,pub,dns,region,p) in rem:
            cmdF = "find app/" + statsdir + " -name start-" + str(n) + "* | wc -l"
            addr = "ubuntu@" + dns
            outF = int(subprocess.run("ssh -i " + pem + " -o " + sshOpt1 + " -o " + sshOpt3 + " -o " + sshOpt4 + " -o " + sshOpt5 + " -ntt " + addr + " " + cmdF, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True).stdout)
            #print("attempting to retrieve 'start' file for" , str(n), ":", outF)
            if 0 < int(outF):
                print("********** process started:" , str(n), "**********")
                remaining.remove((tag,n,i,priv,pub,dns,region,p))

    print("started", len(procsRep), "replicas")
    print("processes that we gave up on:", remaining)

    # we give some time for the replicas to connect before starting the clients
    wait = 5 + int(math.ceil(math.log(numFaults,2)))
    time.sleep(wait)

    for (n,i,priv,pub,dns,region) in instanceClIds:
        sshAdr = "ubuntu@" + dns
        crun2  = client + " " + str(n) + " " + str(numFaults) + " " + str(constFactor) + " " + str(numClTrans) + " " + str(sleepTime) + " " + str(instance)
        crun   = "screen -d -m " + crun2
        cmd    = "\"\"" + srcsgx + " && cd app && rm -f stats/* && " + crun2 + "\"\""
        p      = Popen(["ssh","-i",pem,"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,cmd])
        print("the commandline is {}".format(p.args))
        procsCl.append(("C",n,i,priv,pub,dns,region,p))

    print("started", len(procsCl), "clients")

    totalTime = 0

    if expmode == "TVL":
        while totalTime < cutOffBound:
            copyClientStats(instanceClIds)
            files = glob.glob(statsdir+"/client-throughput-latency-"+str(instance)+"*")
            time.sleep(1)
            totalTime += 1
            if 0 < len(files):
                print("found clients stats", files)
                for (tag,n,i,priv,pub,dns,region,p) in procsRep + procsCl:
                    p.kill()
                break
    else:
        n = 0
        # we stop processes using Python instead of inside the C++ code
        remaining = procsRep.copy()
        while 0 < len(remaining) and totalTime < cutOffBound:
            print("remaining processes at time (", totalTime, "):", remaining)
            rem = remaining.copy()
            for (tag,n,i,priv,pub,dns,region,p) in rem:
                cmdF = "find app/" + statsdir + " -name done-" + str(n) + "* | wc -l"
                addr = "ubuntu@" + dns
                outF = int(subprocess.run("ssh -i " + pem + " -o " + sshOpt1 + " -o " + sshOpt3 + " -o " + sshOpt4 + " -o " + sshOpt5 + " -ntt " + addr + " " + cmdF, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True).stdout)
                #print("attempting to retrieve 'done' file for" , str(n), ":", outF)
                if 0 < int(outF):
                    print("process done:" , str(n))
                    remaining.remove((tag,n,i,priv,pub,dns,region,p))
                    n += 1
                    if (p.poll() is None):
                        p.kill()
            #time.sleep(1)
            totalTime += len(rem)
#        for (tag,n,i,priv,pub,dns,region,p) in procsRep + procsCl:
#            # We stop the execution if it takes too long (cutOffBound)
#            while (p.poll() is None) and totalTime < cutOffBound:
#                time.sleep(1)
#                totalTime += 1
#            n += 1
#            print("processes stopped:", n, "/", len(procsRep + procsCl), "-", p.args)

    global completeRuns
    global abortedRuns
    global aborted

    if totalTime < cutOffBound:
        completeRuns += 1
        print("all", len(procsRep)+len(procsCl), "all processes are done")
    else:
        abortedRuns += 1
        conf = (protocol,numFaults,instance)
        aborted.append(conf)
        f = open(abortedFile, 'a')
        f.write(str(conf)+"\n")
        f.close()
        print("------ reached cutoff bound ------")

    ## cleanup
    for (tag,n,i,priv,pub,dns,region,p) in procsRep + procsCl:
        # we print the nodes that haven't finished yet
        if (p.poll() is None):
            print("killing process still running:",(tag,n,i,priv,pub,dns,region,p.poll()))
            p.kill()
# End of executeInstances


def terminateInstance(region,i):
    while True:
        try:
            subprocess.run(["aws","ec2","terminate-instances","--region",region,"--instance-ids",i], check=True)
            print("terminated:", i)
            return True
        except CalledProcessError:
            print("oops, cannot terminate yet:", i)
            sleep(1)
# End of terminateInstance


def terminateInstances(instanceIds):
    print(">> terminating",str(len(instanceIds)),"instance(s)")
    for (n,i,priv,pub,dns,region) in instanceIds:
        terminateInstance(region,i)
# End of terminateInstances


def terminateAllInstancesRegs(regions):
    for (region,imageID,secGroup) in regions:
        f = open(instFile,'w')
        subprocess.run(["aws","ec2","describe-instances","--region",region,"--filters","Name=image-id,Values="+imageID], stdout=f)
        f.close()
        f = open(instFile,'r')
        instances = json.load(f)
        #print(instances)
        f.close()
        l = instances["Reservations"]
        print("terminating" , str(len(l)), "reservations")
        tot = 0
        for res in l:
            r = res["Instances"]
            print("terminating" , str(len(r)), "instances")
            for inst in r:
                tot += 1
                i = inst["InstanceId"]
                print(i)
                terminateInstance(region,i)
        print("terminated" , str(tot), "instances")
# End of terminateAllInstancesRegs


def terminateAllInstances():
    terminateAllInstancesRegs(regions[1])
# End of terminateAllInstances


def terminateAllInstancesAllRegs():
    terminateAllInstancesRegs(ALLregions)
# End of terminateAllInstancesAllRegs


def testAWS():
    global numMakeCores
    numMakeCores    = 1
    numRepInstances = 1
    numClInstances  = 0
    protocol        = Protocol.CHEAP
    constFactor     = 2
    numFaults       = 1
    instance        = 0

    (instanceRepIds, instanceClIds) = startInstances(numRepInstances,numClInstances)
    makeInstances(instanceRepIds+instanceClIds,protocol)
    executeInstances(instanceRepIds,instanceClIds,protocol,constFactor,numClTrans,sleepTime,numViews,cutOffBound,numFaults,numJoiners,instance)
    terminateInstances(instanceRepIds + instanceClIds)

    terminateAllInstancesAllRegs()
# End of testAWS


def executeAWS(instanceRepIds,instanceClIds,protocol,constFactor,numClTrans,sleepTime,numViews,cutOffBound,numFaults,numJoiners,numDeadNodes):
    print("<<<<<<<<<<<<<<<<<<<<",
          "protocol="+protocol.value,
          ";regions="+regions[0],
          ";payload="+str(payloadSize),
          ";factor="+str(constFactor),
          ";#faults="+str(numFaults),
          ";#joiners="+str(numJoiners),
          "[complete-runs="+str(completeRuns),"aborted-runs="+str(abortedRuns)+"]")
    print("aborted runs so far:", aborted)

    numReps = (constFactor * numFaults) + 1

    print("initial number of nodes:", numReps)
    if deadNodes:
        numReps = numReps - numFaults
    print("number of nodes to actually run:", numReps)

    instanceRepIds = instanceRepIds[0:numReps]

    mkParams(protocol,constFactor,numFaults,numTrans,payloadSize)
    #time.sleep(5)
    makeInstances(instanceRepIds+instanceClIds,protocol)

    for instance in range(repeats):
        #inst = instance * instance2
        #reps = repeats * repeatsL2
        clearStatsDir()
        # execute the experiment
        executeInstances(instanceRepIds,instanceClIds,protocol,constFactor,numClTrans,sleepTime,numViews,cutOffBound,numFaults,numJoiners,instance)

        procs = []
        # copy the stats over
        for (n,i,priv,pub,dns,region) in instanceRepIds:
            sshAdr = "ubuntu@" + dns
            p = Popen(["scp","-i",pem,"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,sshAdr+":/home/ubuntu/app/stats/*","stats/"])
            procs.append((n,i,priv,pub,dns,region,p))

        for (n,i,priv,pub,dns,region,p) in procs:
            while (p.poll() is None):
                time.sleep(1)
            print("stats done:",i)

        (throughputView,latencyView,handle,timeouts,viewSyncMsgs,cryptoSign,cryptoVerif,cryptoNumSign,cryptoNumVerif) = computeStats(protocol,numFaults,numJoiners,numDeadNodes,instance,repeats)
# End of executeAWS


def runAWS():
    global numMakeCores
    numMakeCores = 1

    # Creating stats directory
    Path(statsdir).mkdir(parents=True, exist_ok=True)

    # terminating all instances
    terminateAllInstances()

    printNodePointParams()

    for numFaults in faults:
        for instance2 in range(repeatsL2):
            # starts the instances
            maxNumReps = getMaxNumReps(numFaults) #(3 * numFaults) + 1
            (instanceRepIds, instanceClIds) = startInstances(maxNumReps,numClients)
            copyToInstances(instanceRepIds + instanceClIds)

            numDeadNodes = 0 #numFaults

            # ------
            # HotStuff-like baseline
            if runBase:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.BASE,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
            # ------
            # Cheap-HotStuff (TEE locked/prepared blocks)
            if runCheap:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.CHEAP,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
            # ------
            # Quick-HotStuff (Accumulator)
            if runQuick:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.QUICK,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
            # ------
            # Quick-HotStuff (Accumulator) - debug version
            if runQuickDbg:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.QUICKDBG,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
            # ------
            # Combines Cheap&Quick-HotStuff
            if runComb:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.COMB,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
            # ------
            # Damysus + kinda ROTE
            if runDamr:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.DAMR,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
            # ------
            # Damysus + kinda Achilles
            if runDama:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.DAMA,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
            # ------
            # Damysus + Pacemaker
            if runDamp:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.DAMP,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
            # ------
            # Damysus + Pacemaker + 3f+1 nodes
            if runDamq:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.DAMQ,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
            # ------
            # Free
            if runFree:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.FREE,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
            # ------
            # Rollback prevention
            if runRoll:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.ROLL,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
            # ------
            # Onep
            if runOnep:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.ONEP,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
            # ------
            # OnepB
            if runOnepB:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.ONEPB,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
            # ------
            # OnepC
            if runOnepC:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.ONEPC,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
            # ------
            # OnepD
            if runOnepD:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.ONEPD,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
            # ------
            # Chained HotStuff-like baseline
            if runChBase:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.CHBASE,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
            # ------
            # Chained Cheap&Quick
            if runChComb:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.CHCOMB,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
            # ------
            # Chained Cheap&Quick - debug version
            if runChCombDbg:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.CHCOMBDBG,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
            # ------
            # We now terminate all instances just in case
            #terminateAllInstances()

            # terminates the instances
            terminateInstances(instanceRepIds + instanceClIds)

    print("num complete runs=", completeRuns)
    print("num aborted runs=", abortedRuns)
    print("aborted runs:", aborted)

    createPlot(pointsFile)
# End of runAWS


def getMaxNumReps(numFaults):
    maxNumReps = (2 * numFaults) + 1
    if runBase or runQuick or runQuickDbg or runDamq or runChBase:
        maxNumReps = (3 * numFaults) + 1
    return maxNumReps

## For p9 - to run experiments where we vary the number of nodes trying to rejoin the system
def runAWSJoin(numFaults,joiners):
    global numMakeCores
    numMakeCores = 1

    # Creating stats directory
    Path(statsdir).mkdir(parents=True, exist_ok=True)

    # terminating all instances
    terminateAllInstances()

    printNodePointParams()

    print("will test the following number of joiners: ", joiners)

    for j in joiners:
        print("number of joiners: ", j)

        for instance2 in range(repeatsL2):
            # starts the instances
            maxNumReps = getMaxNumReps(numFaults)
            (instanceRepIds, instanceClIds) = startInstances(maxNumReps,numClients)
            copyToInstances(instanceRepIds + instanceClIds)

            numDeadNodes = 0 #numFaults

            # ------
            # HotStuff-like baseline
            if runBase:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.BASE,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes)
            # ------
            # Cheap-HotStuff (TEE locked/prepared blocks)
            if runCheap:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.CHEAP,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes)
            # ------
            # Quick-HotStuff (Accumulator)
            if runQuick:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.QUICK,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes)
            # ------
            # Quick-HotStuff (Accumulator) - debug version
            if runQuickDbg:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.QUICKDBG,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes)
            # ------
            # Combines Cheap&Quick-HotStuff
            if runComb:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.COMB,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes)
            # ------
            # Damysus + kinda ROTE
            if runDamr:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.DAMR,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes)
            # ------
            # Damysus + kinda Achilles
            if runDama:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.DAMA,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes)
            # ------
            # Damysus + Pacemaker
            if runDamp:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.DAMP,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes)
            # ------
            # Damysus + Pacemaker + 3f+1 nodes
            if runDamq:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.DAMQ,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes)
            # ------
            # Free
            if runFree:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.FREE,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes)
            # ------
            # Rollback prevention
            if runRoll:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.ROLL,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes)
            # ------
            # Onep
            if runOnep:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.ONEP,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes)
            # ------
            # OnepB
            if runOnepB:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.ONEPB,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes)
            # ------
            # OnepC
            if runOnepC:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.ONEPC,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes)
            # ------
            # OnepD
            if runOnepD:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.ONEPD,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes)
            # ------
            # Chained HotStuff-like baseline
            if runChBase:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.CHBASE,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes)
            # ------
            # Chained Cheap&Quick
            if runChComb:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.CHCOMB,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes)
            # ------
            # Chained Cheap&Quick - debug version
            if runChCombDbg:
                executeAWS(instanceRepIds=instanceRepIds,instanceClIds=instanceClIds,protocol=Protocol.CHCOMBDBG,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes)
            # ------
            # We now terminate all instances just in case
            #terminateAllInstances()

            # terminates the instances
            terminateInstances(instanceRepIds + instanceClIds)

    print("num complete runs=", completeRuns)
    print("num aborted runs=", abortedRuns)
    print("aborted runs:", aborted)

    createPlot(pointsFile)
# End of runAWS


# nodes contains the nodes' information
def startRemoteContainers(nodes,numReps,numClients):
    print("running in docker mode, starting" , numReps, "containers for the replicas and", numClients, "for the clients")

    global ipsOfNodes

    lr = list(map(lambda x: (True,  x, str(x)), list(range(numReps))))            # replicas
    lc = list(map(lambda x: (False, x, "c" + str(x)), list(range(numClients))))  # clients
    lall = lr + lc

    instanceRepIds = []
    instanceClIds  = []

    for (isRep, n, i) in lall:
        #
        # we cycle through the nodes
        node  = nodes[0]
        nodes = nodes[1:]
        nodes.append(node)
        #
        # We stop and remove the Doker instance if it is still exists
        instance = dockerBase + i
        stop_cmd = docker + " stop " + instance
        rm_cmd   = docker + " rm " + instance
        sshAdr   = node["user"] + "@" + node["host"]
        s1 = Popen(["ssh","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,stop_cmd + "; " + rm_cmd])
        print("the commandline is {}".format(s1.args))
        s1.communicate()
        #
        # We start the Docker instance
        # TODO: make sure to cover all the ports
        opt1 = "--expose=8000-9999"
        opt2 = "--network=" + clusterNet
        opt3 = "--cap-add=NET_ADMIN"
        opt4 = "--name " + instance
        opts = " ".join([opt1, opt2, opt3, opt4])
        run_cmd = docker + " run -td " + opts + " " + dockerBase
        s2 = Popen(["ssh","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,run_cmd])
        print("the commandline is {}".format(s2.args))
        s2.communicate()
        #
        exec_cmd = docker + " exec -t " + instance + " bash -c \"" + srcsgx + "; mkdir " + statsdir + "\""
        s3 = Popen(["ssh","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,exec_cmd])
        print("the commandline is {}".format(s3.args))
        s3.communicate()
        #
        # Set the network latency
        if 0 < networkLat:
            print("----changing network latency to " + str(networkLat) + "ms")
            correlation=100
            dist="normal" #"uniform"
            tc_cmd = "tc qdisc add dev eth0 root netem delay " + str(networkLat) + "ms " + str(networkVar) + "ms " + str(correlation) +"% distribution " + dist + " loss " + str(msgLoss) + "%"
            lat_cmd = docker + " exec -t " + instance + " bash -c \"" + tc_cmd + "\""
            s4 = Popen(["ssh","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,lat_cmd])
            print("the commandline is {}".format(s4.args))
            s4.communicate()
        #
        # Extract the IP address of the container
        address = instance + "_addr"
        ip_cmd = "cd " + node["dir"] + "; " + docker + " inspect " + instance + " | jq '.[].NetworkSettings.Networks." + clusterNet + ".IPAddress' > " + address
        s5 = Popen(["ssh","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,ip_cmd])
        print("the commandline is {}".format(s5.args))
        s5.communicate()
        #
        s6 = Popen(["scp","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,sshAdr+":"+node["dir"]+"/"+address,address])
        print("the commandline is {}".format(s6.args))
        s6.communicate()
        #
        rm_cmd = "cd " + node["dir"] + "; rm " + address
        s7 = Popen(["ssh","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,rm_cmd])
        print("the commandline is {}".format(s7.args))
        s7.communicate()
        #
        with open(address, 'r') as f:
            data = f.read()
            #print(data)
            srch = re.search('\"(.+?)\"', data)
            if srch:
                out = srch.group(1)
                print("----container's address:" + out)
                if isRep:
                    ipsOfNodes.update({n:out})
                    instanceRepIds.append((n,i,node))
                else:
                    instanceClIds.append((n,i,node))
            else:
                print("----container's address: UNKNOWN")
        subprocess.run(["rm " + address], shell=True, check=True)

    genLocalConf(numReps,addresses)

    for (n,i,node) in instanceRepIds + instanceClIds:
        #
        dockerInstance = dockerBase + i
        sshAdr = node["user"] + "@" + node["host"]
        #
        s1 = Popen(["scp","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,addresses,sshAdr+":"+node["dir"]+"/"+addresses])
        print("the commandline is {}".format(s1.args))
        s1.communicate()
        #
        cp_cmd = docker + " cp " + node["dir"]+"/"+addresses + " " + dockerInstance + ":/app/"
        s2 = Popen(["ssh","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,cp_cmd])
        print("the commandline is {}".format(s2.args))
        s2.communicate()

    return (instanceRepIds, instanceClIds)
## End of startRemoteContainers


def makeCluster(instanceIds,protocol):
    ncores = 1
    if useMultiCores:
        ncores = numMakeCores
    print(">> making",str(len(instanceIds)),"instance(s) using",str(ncores),"core(s)")

    procs  = []
    make0  = "make -j "+str(ncores)
    make   = make0 + " SGX_MODE="+sgxmode if needsSGX(protocol) else make0 + " server client"

    for (n,i,node) in instanceIds:
        #
        dockerInstance = dockerBase + i
        sshAdr = node["user"] + "@" + node["host"]
        s1 = Popen(["scp","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,params,sshAdr+":"+node["dir"]+"/params.h"])
        print("the commandline is {}".format(s1.args))
        s1.communicate()
        #
        cp_cmd = docker + " cp " + node["dir"]+"/params.h" + " " + dockerInstance + ":/app/App/"
        s2 = Popen(["ssh","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,cp_cmd])
        print("the commandline is {}".format(s2.args))
        s2.communicate()
        #
        make_cmd = docker + " exec -t " + dockerInstance + " bash -c \"" + srcsgx + "; make clean; " + make + "\""
        s3 = Popen(["ssh","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,make_cmd])
        print("the commandline is {}".format(s3.args))
        #s3.communicate()
        procs.append((n,i,node,s3))

    for (n,i,node,p) in procs:
        while (p.poll() is None):
            time.sleep(1)
        print("process done:",i)

    print("all instances are made")
# End of makeCluster


def executeClusterInstances(instanceRepIds,instanceClIds,protocol,constFactor,numClTrans,sleepTime,numViews,cutOffBound,numFaults,instance):
    print(">> connecting to",str(len(instanceRepIds)),"replica instance(s)")
    print(">> connecting to",str(len(instanceClIds)),"client instance(s)")

    procsRep   = []
    procsCl    = []
    newtimeout = int(math.ceil(timeout+math.log(numFaults,2)))
    server     = "./sgxserver" if needsSGX(protocol) else "./server"
    client     = "./sgxclient" if needsSGX(protocol) else "./client"

    for (n,i,node) in instanceRepIds:
        # we give some time for the nodes to connect gradually
        if (n%10 == 5):
            time.sleep(2)
        dockerI = dockerBase + i
        sshAdr  = node["user"] + "@" + node["host"]
        srun    = " ".join([server,str(n),str(numFaults),str(constFactor),str(numViews),str(newtimeout),str(timeoutMul),str(timeoutDiv),str(opdist),str(syncPeriod),str(joinPeriod),str(numJoiners),str(quantileSize1),str(quantileSize2),str(skipViews)])
        run_cmd = docker + " exec -t " + dockerI + " bash -c \"" + srcsgx + "; rm -f stats/*; " + srun + "\""
        s1 = Popen(["ssh","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,run_cmd])
        print("the commandline is {}".format(s1.args))
        #s1.communicate()
        procsRep.append(("R",n,i,node,s1))

    print("started", len(procsRep), "replicas")

    # we give some time for the replicas to connect before starting the clients
    wait = 5 + int(math.ceil(math.log(numFaults,2)))
    time.sleep(wait)

    for (n,i,node) in instanceClIds:
        dockerI = dockerBase + i
        sshAdr  = node["user"] + "@" + node["host"]
        crun    = " ".join([client,str(n),str(numFaults),str(constFactor),str(numClTrans),str(sleepTime),str(instance)])
        run_cmd = docker + " exec -t " + dockerI + " bash -c \"" + srcsgx + "; rm -f stats/*; " + crun + "\""
        s1 = Popen(["ssh","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,run_cmd])
        print("the commandline is {}".format(s1.args))
        #s1.communicate()
        procsCl.append(("C",n,i,node,s1))

    print("started", len(procsCl), "clients")

    totalTime = 0

    if expmode == "TVL":
        print("TO FIX: TVL option")
        ## TODO
        # while totalTime < cutOffBound:
        #     copyClientStats(instanceClIds)
        #     files = glob.glob(statsdir+"/client-throughput-latency-"+str(instance)+"*")
        #     time.sleep(1)
        #     totalTime += 1
        #     if 0 < len(files):
        #         print("found clients stats", files)
        #         for (tag,n,i,priv,pub,dns,region,p) in procsRep + procsCl:
        #             p.kill()
        #         break
    else:
        remaining = procsRep.copy()
        # We wait here for all processes to complete
        # but we stop the execution if it takes too long (cutOffBound)
        while 0 < len(remaining) and totalTime < cutOffBound:
            print("remaining processes:", remaining)
            # We filter out the ones that are done. x is of the form (t,i,p)
            rem = remaining.copy()
            for (tag,n,i,node,p) in rem:
                sshAdr    = node["user"] + "@" + node["host"]
                dockerI   = dockerBase + str(i)
                find_done = "find /app/" + statsdir + " -name done-" + str(i) + "* | wc -l"
                doneFile  = "done" + str(i)
                find_cmd  = "cd " + node["dir"] + "; " + docker + " exec -t " + dockerI + " bash -c \"" + find_done + "\" > " + doneFile
                s1 = Popen(["ssh","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,find_cmd])
                print("the commandline is {}".format(s1.args))
                s1.communicate()
                #
                s2 = Popen(["scp","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,sshAdr+":"+node["dir"]+"/"+doneFile,doneFile])
                print("the commandline is {}".format(s2.args))
                s2.communicate()
                #
                rm_cmd = "cd " + node["dir"] + "; rm " + doneFile
                s3 = Popen(["ssh","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,rm_cmd])
                print("the commandline is {}".format(s3.args))
                s3.communicate()
                with open(doneFile, 'r') as f:
                    out = f.read()
                    print("******" + out + "******")
                    if 0 < int(out):
                        remaining.remove((tag,n,i,node,p))
                subprocess.run(["rm " + doneFile], shell=True, check=True)
            time.sleep(1)
            totalTime += 1

    global completeRuns
    global abortedRuns
    global aborted

    if totalTime < cutOffBound:
        completeRuns += 1
        print("all", len(procsRep)+len(procsCl), "processes are done")
    else:
        abortedRuns += 1
        conf = (protocol,numFaults,instance)
        aborted.append(conf)
        f = open(abortedFile, 'a')
        f.write(str(conf)+"\n")
        f.close()
        print("------ reached cutoff bound ------")


    ## cleanup
    # kill python subprocesses
    for (tag,n,i,node,p) in procsRep + procsCl:
        # we print the nodes that haven't finished yet
        if (p.poll() is None):
            print("still running:",(tag,n,i,node,p.poll()))
            p.kill()

    ports = " ".join(list(map(lambda port: str(port) + "/tcp", allLocalPorts)))

    # we kill the processes & copy+remove the stats file to this machine
    for (tag,n,i,node,p) in procsRep + procsCl:
        sshAdr   = node["user"] + "@" + node["host"]
        dockerI  = dockerBase + i
        #
        kill_all = "killall -q sgxserver sgxclient server client; fuser -k " + ports
        kill_cmd = docker + " exec -t " + dockerI + " bash -c \"" + kill_all + "\""
        s1 = Popen(["ssh","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,kill_cmd])
        print("the commandline is {}".format(s1.args))
        s1.communicate()
        #
        src = dockerI + ":/app/" + statsdir + "/."
        dst = statsdir + "/"
        cp_cmd = "cd " + node["dir"] + "; mkdir " + statsdir + "; " + docker + " cp " + src + " " + dst
        s2 = Popen(["ssh","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,cp_cmd])
        print("the commandline is {}".format(s2.args))
        s2.communicate()
        #
        subprocess.run(["scp","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,sshAdr+":"+node["dir"]+"/stats/*","stats/"])
        #
        rcmd = "rm /app/" + statsdir + "/*"
        docker_rm_cmd = docker + " exec -t " + dockerI + " bash -c \"" + rcmd + "\""
        rm_cmd = "cd " + node["dir"] + "; rm -Rf " + statsdir + "; " + docker_rm_cmd
        s3 = Popen(["ssh","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,rm_cmd])
        print("the commandline is {}".format(s3.args))
        s3.communicate()
# End of executeClusterInstances


def executeCluster(info,protocol,constFactor,numClTrans,sleepTime,numViews,cutOffBound,numFaults,numJoiners,numDeadNodes):
    print("<<<<<<<<<<<<<<<<<<<<",
          "protocol="+protocol.value,
          ";payload="+str(payloadSize),
          ";factor="+str(constFactor),
          ";#faults="+str(numFaults),
          "[complete-runs="+str(completeRuns),"aborted-runs="+str(abortedRuns)+"]")
    print("aborted runs so far:", aborted)

    numReps = (constFactor * numFaults) + 1

    print("initial number of nodes:", numReps)
    if deadNodes:
        numReps = numReps - numFaults
    print("number of nodes to actually run:", numReps)

    # starts the containers
    (instanceRepIds,instanceClIds) = startRemoteContainers(info["nodes"],numReps,numClients)
    mkParams(protocol,constFactor,numFaults,numTrans,payloadSize)
    # make all nodes
    makeCluster(instanceRepIds+instanceClIds,protocol)

    for instance in range(repeats):
        clearStatsDir()
        # execute the experiment
        executeClusterInstances(instanceRepIds,instanceClIds,protocol,constFactor,numClTrans,sleepTime,numViews,cutOffBound,numFaults,instance)
        (throughputView,latencyView,handle,timeouts,viewSyncMsgs,cryptoSign,cryptoVerif,cryptoNumSign,cryptoNumVerif) = computeStats(protocol,numFaults,numJoiners,numDeadNodes,instance,repeats)

    for (n,i,node) in instanceRepIds + instanceClIds:
        instance = dockerBase + i
        stop_cmd = docker + " stop " + instance
        rm_cmd   = docker + " rm " + instance
        sshAdr   = node["user"] + "@" + node["host"]
        s1 = Popen(["ssh","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,stop_cmd + "; " + rm_cmd])
        print("the commandline is {}".format(s1.args))
        s1.communicate()
# End of executeCluster


def runCluster():
    global numMakeCores
    nuMakeCores = 1

    # Creating stats directory
    Path(statsdir).mkdir(parents=True, exist_ok=True)

    printNodePointParams()

    f = open(clusterFile,'r')
    info = json.load(f)
    f.close()

    nodes = info["nodes"]

    init_cmd  = docker + " swarm init"
    leave_cmd = docker + " swarm leave --force"

    # Leave all swarms before starting
    for node in nodes:
        sshAdr = node["user"] + "@" + node["host"]
        s1 = Popen(["ssh","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,leave_cmd])
        print("the commandline is {}".format(s1.args))
        s1.communicate()
    subprocess.run([leave_cmd], shell=True) #, check=True)

    srch = re.search('.*(docker swarm join .+)', subprocess.run(init_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True).stdout)
    if srch:
        join_cmd = srch.group(1)
        print("----join command:" + join_cmd)
        for node in nodes:
            sshAdr = node["user"] + "@" + node["host"]
            s1 = Popen(["ssh","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,join_cmd])
            print("the commandline is {}".format(s1.args))
            s1.communicate()
        net_cmd = docker + " network create --driver=overlay --attachable " + clusterNet
        subprocess.run([net_cmd], shell=True, check=True)
    else:
        print("----no join command")

    for numFaults in faults:
        numDeadNodes = 0 #numFaults

        # ------
        # HotStuff-like baseline
        if runBase:
            executeCluster(info=info,protocol=Protocol.BASE,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
        # ------
        # Cheap-HotStuff (TEE locked/prepared blocks)
        if runCheap:
            executeCluster(info=info,protocol=Protocol.CHEAP,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
        # ------
        # Quick-HotStuff (Accumulator)
        if runQuick:
            executeCluster(info=info,protocol=Protocol.QUICK,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
        # ------
        # Quick-HotStuff (Accumulator) - debug version
        if runQuickDbg:
            executeCluster(info=info,protocol=Protocol.QUICKDBG,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
        # ------
        # Combines Cheap&Quick-HotStuff
        if runComb:
            executeCluster(info=info,protocol=Protocol.COMB,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
        # ------
        # Damysus + kinda ROTE
        if runDamr:
            executeCluster(info=info,protocol=Protocol.DAMR,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
        # ------
        # Damysus + kinda Achilles
        if runDama:
            executeCluster(info=info,protocol=Protocol.DAMA,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
        # ------
        # Damysus + Pacemaker
        if runDamp:
            executeCluster(info=info,protocol=Protocol.DAMP,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
        # ------
        # Damysus + Pacemaker + 3f+1 nodes
        if runDamq:
            executeCluster(info=info,protocol=Protocol.DAMQ,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
        # ------
        # Free
        if runFree:
            executeCluster(info=info,protocol=Protocol.FREE,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
        # ------
        # Roll
        if runRoll:
            executeCluster(info=info,protocol=Protocol.ROLL,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
        # ------
        # Onep
        if runOnep:
            executeCluster(info=info,protocol=Protocol.ONEP,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
        # ------
        # OnepB
        if runOnepB:
            executeCluster(info=info,protocol=Protocol.ONEPB,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
        # ------
        # OnepC
        if runOnepC:
            executeCluster(info=info,protocol=Protocol.ONEPC,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
        # ------
        # OnepD
        if runOnepD:
            executeCluster(info=info,protocol=Protocol.ONEPD,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
        # ------
        # Chained HotStuff-like baseline
        if runChBase:
            executeCluster(info=info,protocol=Protocol.CHBASE,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
        # ------
        # Chained Cheap&Quick
        if runChComb:
            executeCluster(info=info,protocol=Protocol.CHCOMB,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)
        # ------
        # Chained Cheap&Quick - debug version
        if runChCombDbg:
            executeCluster(info=info,protocol=Protocol.CHCOMBDBG,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes)

    # cleanup
    for node in nodes:
        sshAdr = node["user"] + "@" + node["host"]
        s1 = Popen(["ssh","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,leave_cmd])
        print("the commandline is {}".format(s1.args))
        s1.communicate()
    subprocess.run([leave_cmd], shell=True) #, check=True)
    subprocess.run([docker + " network rm " + clusterNet], shell=True) #, check=True)

    print("num complete runs=", completeRuns)
    print("num aborted runs=", abortedRuns)
    print("aborted runs:", aborted)

    createPlot(pointsFile)
# End of runCluster


def prepareCluster():
    f = open(clusterFile,'r')
    info = json.load(f)
    f.close()

    nodes = info["nodes"]
    procs = []
    for node in nodes:
        sshAdr = node["user"] + "@" + node["host"]
        prep_cmd = "cd " + node["dir"] + "; git clone https://github.com/vrahli/damysus.git; cd damysus; docker build -t damysus ."
        s = Popen(["ssh","-i",node["key"],"-o",sshOpt1,"-o",sshOpt3,"-o",sshOpt4,"-o",sshOpt5,"-ntt",sshAdr,prep_cmd])
        procs.append((node,s))

    for (node,p) in procs:
        while (p.poll() is None):
            time.sleep(1)
        print("docker container built for node:",node["node"])
# End of prepareCluster


## Returns True if the protocol requires SGX
def needsSGX(protocol):
    if (protocol in [Protocol.BASE, Protocol.CHBASE, Protocol.QUICKDBG, Protocol.CHCOMBDBG]):
        return False
    else:
        return True
# End of needsSGX


def clearStatsDir():
    # Removing all (temporary) files in stats dir
    files0 = glob.glob(statsdir+"/vals*")
    files1 = glob.glob(statsdir+"/throughput-view*")
    files2 = glob.glob(statsdir+"/latency-view*")
    files3 = glob.glob(statsdir+"/handle*")
    files4 = glob.glob(statsdir+"/crypto*")
    files5 = glob.glob(statsdir+"/done*")
    files6 = glob.glob(statsdir+"/client-throughput-latency*")
    files7 = glob.glob(statsdir+"/times*")
    for f in files0 + files1 + files2 + files3 + files4 + files5 + files6 + files7:
        #print(f)
        os.remove(f)
# End of clearStatsDir


def mkParams(protocol,constFactor,numFaults,numTrans,payloadSize):
    f = open(params, 'w')
    f.write("#ifndef PARAMS_H\n")
    f.write("#define PARAMS_H\n")
    f.write("\n")
    f.write("#define " + protocol.value + "\n")
    f.write("#define MAX_NUM_NODES " + str((constFactor*numFaults)+1) + "\n")
    f.write("#define MAX_NUM_SIGNATURES " + str((constFactor*numFaults)+1-numFaults) + "\n")
    f.write("#define MAX_NUM_TRANSACTIONS " + str(numTrans) + "\n")
    f.write("#define PAYLOAD_SIZE " +str(payloadSize) + "\n")
    f.write("\n")
    f.write("#endif\n")
    f.close()
# End of mkParams


def mkApp(protocol,constFactor,numFaults,numTrans,payloadSize):
    ncores = 1
    if useMultiCores:
        ncores = numMakeCores
    print(">> making using",str(ncores),"core(s)")

    mkParams(protocol,constFactor,numFaults,numTrans,payloadSize)

    if runDocker:
        # make 1 instance: the "x" instance
        instancex = dockerBase + "x"
        adstx     = instancex + ":/app/App/"
        edstx     = instancex + ":/app/Enclave/"
        subprocess.run([docker + " cp Makefile "  + instancex + ":/app/"], shell=True, check=True)
        subprocess.run([docker + " cp App/. "     + adstx], shell=True, check=True)
        subprocess.run([docker + " cp Enclave/. " + edstx], shell=True, check=True)
        subprocess.run([docker + " exec -t " + instancex + " bash -c \"make clean\""], shell=True, check=True)
        if needsSGX(protocol):
            print("protocol needs SGX")
            subprocess.run([docker + " exec -t " + instancex + " bash -c \"" + srcsgx + "; make -j " + str(ncores) + " SGX_MODE=" + sgxmode + "\""], shell=True, check=True)
        else:
            print("protocol doesn't need SGX")
            subprocess.run([docker + " exec -t " + instancex + " bash -c \"make -j " + str(ncores) + " server client\""], shell=True, check=True)

        tmp = "docker_tmp"
        Path(tmp).mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run([docker + " cp " + instancex + ":/app/." + " " + tmp + "/"], shell=True, check=True)

            # copy the files over to the other instances
            numReps = (constFactor * numFaults) + 1
            lr = list(map(lambda x: str(x), list(range(numReps))))           # replicas
            lc = list(map(lambda x: "c" + str(x), list(range(numClients))))  # clients
            for i in lr + lc:
                instance = dockerBase + i
                print("copying files from " + instancex + " to " + instance)
                subprocess.run([docker + " cp " + tmp + "/." + " " + instance + ":/app/"], shell=True, check=True)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    else:
        subprocess.check_call(["make","clean"])
        if needsSGX(protocol):
            buildCmd = (srcsgx
                        + '; make SGX_MODE=' + sgxmode
                        + ' SGX_SDK="$SGX_SDK"'
                        + ' SGXSSL_INCLUDE_PATH="$SGXSSL_INCLUDE_PATH"'
                        + ' SGXSSL_UNTRUSTED_LIB_PATH="$SGXSSL_UNTRUSTED_LIB_PATH"'
                        + ' SGXSSL_TRUSTED_LIB_PATH="$SGXSSL_TRUSTED_LIB_PATH"'
                        + ' -j2')
            subprocess.run(["bash", "-lc", buildCmd], check=True)
        else:
            subprocess.check_call(["make","-j",str(ncores),"server","client"])
# End of mkApp


def execute(protocol,constFactor,numClTrans,sleepTime,numViews,cutOffBound,numFaults,numDeadNodes,numJoiners,instance):
    subsReps    = [] # list of replica subprocesses
    subsClients = [] # list of client subprocesses
    numReps = (constFactor * numFaults) + 1

    instanceRepIds = []
    instanceClIds  = []
    if runDas5:
        (instanceRepIds, instanceClIds) = startDas5Processes(numReps,numClients)
    else:
        genLocalConf(numReps,addresses)

    print("initial number of nodes:", numReps)
    if numDeadNodes > 0:
        numReps = numReps - numDeadNodes
        if runDas5:
            instanceRepIds = instanceRepIds[:numReps]
    print("number of nodes to actually run:", numReps)


    lr = list(map(lambda x: str(x), list(range(numReps))))           # replicas
    lc = list(map(lambda x: "c" + str(x), list(range(numClients))))  # clients
    lall = lr + lc

    # if running in docker mode, we copy the addresses to the containers
    if runDocker:
        for i in lall:
            dockerInstance = dockerBase + i
            dst = dockerInstance + ":/app/"
            subprocess.run([docker + " cp " + addresses + " " + dst], shell=True, check=True)

    server = "./sgxserver" if needsSGX(protocol) else "./server"
    client = "./sgxclient" if needsSGX(protocol) else "./client"

    newtimeout = timeout #int(math.ceil(timeout+math.log(numFaults,2)))
    print("timeout change: ", str(timeout), " -> " , str (newtimeout))
    # starting severs
    for i in range(numReps):
        # we give some time for the nodes to connect gradually
        if (i%10 == 5):
            time.sleep(2)
        cmd = " ".join([server, str(i), str(numFaults), str(constFactor), str(numViews), str(newtimeout), str(timeoutMul), str(timeoutDiv), str(opdist), str(syncPeriod), str(joinPeriod), str(numJoiners), str(quantileSize1), str(quantileSize2), str(skipViews)])
        if runDocker:
            dockerInstance = dockerBase + str(i)
            if needsSGX(protocol):
                cmd = srcsgx + "; " + cmd
            cmd = docker + " exec -t " + dockerInstance + " bash -c \"" + cmd + "\""
        if runDas5:
            host = instanceRepIds[i][1]
            if needsSGX(protocol):
                cmd = srcsgx + "; " + cmd
            p = runOnDas5Node(host, cmd)
        else:
            p = Popen(cmd, shell=True)
        subsReps.append(("R",i,p))

    print("started", len(subsReps), "replicas")

    # starting client after a few seconds
    # TODO? instead watch the ouput from above until we've seen enough established connections
    #wait = 20 + int(math.ceil(math.log(numFaults,2)))
    wait = 5 + int(math.ceil(math.log(numFaults,2)))
    #sfact = 4 if numFaults < 2 else (3 if numFaults < 4 else (2 if numFaults < 6 else 1))
    #wait = sfact*numFaults
    time.sleep(wait)
    for cid in range(numClients):
        cmd = " ".join([client, str(cid), str(numFaults), str(constFactor), str(numClTrans), str(sleepTime), str(instance)])
        if runDocker:
            dockerInstance = dockerBase + "c" + str(cid)
            if needsSGX(protocol):
                cmd = srcsgx + "; " + cmd
            cmd = docker + " exec -t " + dockerInstance + " bash -c \"" + cmd + "\""
        if runDas5:
            host = instanceClIds[cid][1]
            if needsSGX(protocol):
                cmd = srcsgx + "; " + cmd
            c = runOnDas5Node(host, cmd)
        else:
            c = Popen(cmd, shell=True)
        subsClients.append(("C",cid,c))

    print("started", len(subsClients), "clients")

    totalTime = 0

    if expmode == "TVL":
        remaining = subsClients.copy()
        numTotClients = len(subsClients)
        while 0 < len(remaining) and totalTime < cutOffBound:
            print(str(len(remaining)) + " remaining clients out of " + str(numTotClients) + ":", remaining)
            cFileBase = "client-throughput-latency-" + str(instance)
            if runDocker:
                rem = remaining.copy()
                for (t,i,p) in rem:
                    cFile = cFileBase + "-" + str(i) + "*"
                    dockerInstance = dockerBase + "c" + str(i)
                    cmd = "find /app/" + statsdir + " -name " + cFile + " | wc -l"
                    out = int(subprocess.run(docker + " exec -t " + dockerInstance + " bash -c \"" + cmd + "\"", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True).stdout)
                    if 0 < int(out):
                        print("found clients stats for client ", str(i))
                        remaining.remove((t,i,p))
            else:
                remaining = list(filter(lambda x: 0 == len(glob.glob(statsdir + "/" + cFileBase + "-" + str(x[1]) + "*")), remaining))
                #files = glob.glob(statsdir+"/client-throughput-latency-"+str(instance)+"*")
                #numFiles = len(files)
            time.sleep(1)
            totalTime += 1
        for (t,i,p) in subsReps + subsClients:
            p.kill()
    else:
        remaining = subsReps.copy()
        # We wait here for all processes to complete
        #     | We also want to allow numJoiners to not be done since they might be waiting to rejoin
        #     | a session but the other nodes are already done, i.e., replace 0 with numJoiners.
        # but we stop the execution if it takes too long (cutOffBound)
        while numJoiners < len(remaining) and totalTime < cutOffBound:
            print("remaining processes:", remaining)
            # We filter out the ones that are done. x is of the form (t,i,p)
            if runDocker:
                rem = remaining.copy()
                for (t,i,p) in rem:
                    dockerInstance = dockerBase + str(i)
                    cmd = "find /app/" + statsdir + " -name done-" + str(i) + "* | wc -l"
                    out = int(subprocess.run(docker + " exec -t " + dockerInstance + " bash -c \"" + cmd + "\"", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True).stdout)
                    if 0 < int(out):
                        remaining.remove((t,i,p))
            else:
                remaining = list(filter(lambda x: 0 == len(glob.glob(statsdir+"/done-"+str(x[1])+"*")), remaining))
            time.sleep(1)
            totalTime += 1

    global completeRuns
    global abortedRuns
    global aborted

    if totalTime < cutOffBound:
        completeRuns += 1
        print("enough processes are done:", len(remaining) , "remaining amongst", len(subsReps)+len(subsClients))
    else:
        abortedRuns += 1
        conf = (protocol,numFaults,instance)
        aborted.append(conf)
        f = open(abortedFile, 'a')
        f.write(str(conf)+"\n")
        f.close()
        print("------ reached cutoff bound ------")

    ## cleanup
    # kill python subprocesses
    for (t,i,p) in subsReps + subsClients:
        # we print the nodes that haven't finished yet
        if (p.poll() is None):
            print("still running:",(t,i,p.poll()))
            p.kill()

    ports = " ".join(list(map(lambda port: str(port) + "/tcp", allLocalPorts)))

    # kill processes
    if runDocker:
        # if running in docker mode, we kill the processes & copy+remove the stats file to this machine
        for i in lall:
            dockerInstance = dockerBase + i
            kcmd = "killall -q sgxserver sgxclient server client; fuser -k " + ports
            subprocess.run([docker + " exec -t " + dockerInstance + " bash -c \"" + kcmd + "\""], shell=True) #, check=True)
            #print("*** copying stat files ***")
            #subprocess.run([docker + " exec -t " + dockerInstance + " bash -c \"ls /app/" + statsdir + "\""], shell=True) #, check=True)
            src = dockerInstance + ":/app/" + statsdir + "/."
            dst = statsdir + "/"
            subprocess.run([docker + " cp " + src + " " + dst], shell=True, check=True)
            rcmd = "rm /app/" + statsdir + "/*"
            subprocess.run([docker + " exec -t " + dockerInstance + " bash -c \"" + rcmd + "\""], shell=True) #, check=True)
    elif runDas5:
        nodes = set(map(lambda x: x[1], instanceRepIds + instanceClIds))
        kill_all = "killall -q sgxserver sgxclient server client; true"
        for node in nodes:
            k = runOnDas5Node(node, kill_all)
            k.communicate()
    else:
        subprocess.run(["killall -q sgxserver sgxclient server client; fuser -k " + ports], shell=True) #, check=True)
## End of execute


def printNodePoint(protocol,numFaults,numJoiners,numDeadNodes,tag,val):
    f = open(pointsFile, 'a')
    f.write("protocol="+protocol.value+" "+"faults="+str(numFaults)+" "+"joiners="+str(numJoiners)+" "+"dead="+str(numDeadNodes)+" "+tag+"="+str(val)+"\n")
    f.close()
# End of printNodePoint


def printNodePointComment(protocol,numFaults,numJoiners,instance,repeats):
    f = open(pointsFile, 'a')
    f.write("# protocol="+protocol.value+" regions="+regions[0]+" payload="+str(payloadSize)+" faults="+str(numFaults)+" joiners="+str(numJoiners)+" instance="+str(instance)+" repeats="+str(repeats)+"\n")
    f.close()
# End of printNodePointComment


def printNodePointParams():
    f = open(pointsFile, 'a')
    text = "##params"
    text += " cpus="+str(dockerCpu)
    text += " mem="+str(dockerMem)
    text += " lat="+str(networkLat)
    text += " rate="+str(rateMbit)
    text += " payload="+str(payloadSize)
    text += " repeats1="+str(repeats)
    text += " repeats2="+str(repeatsL2)
    text += " views="+str(numViews)
    text += " regions="+regions[0]
    text += "\n"
    f.write(text)
    f.close()
# End of printNodePointParams


def computeStats(protocol,numFaults,numJoiners,numDeadNodes,instance,repeats):
    # Computing throughput and latency
    throughputViewVal=0.0
    throughputViewNum=0
    latencyViewVal=0.0
    latencyViewNum=0

    handleVal=0.0
    handleNum=0

    tosVal=0
    tosNum=0

    pbsVal=0
    pbsNum=0

    pcsVal=0
    pcsNum=0

    viewSyncMsgsVal=0
    viewSyncMsgsNum=0

    cryptoSignVal=0.0
    cryptoSignNum=0

    cryptoVerifVal=0.0
    cryptoVerifNum=0

    cryptoNumSignVal=0.0
    cryptoNumSignNum=0

    cryptoNumVerifVal=0.0
    cryptoNumVerifNum=0

    printNodePointComment(protocol,numFaults,numJoiners,instance,repeats)

    files = glob.glob(statsdir+"/*")
    for filename in files:
        if filename.startswith(statsdir+"/times"):
            f = open(filename, "r")
            s = f.read()
            f.close()
            #
            g = open(timesFile, 'a')
            g.write(protocol.value+" "+str(numFaults)+" "+s+"\n")
            g.close()
        if filename.startswith(statsdir+"/vals"):
            f = open(filename, "r")
            s = f.read()
            f.close()
            l = s.split()
            if not(len(l) == 10 or len(l) == 11):
                print("wrong vals file:", filename)
            else:
                if len(l) == 11:
                    [thru,lat,hdl,tos,pbs,pcs,viewSyncMsgs,signNum,signTime,verifNum,verifTime] = l
                else:
                    [thru,lat,hdl,tos,pbs,pcs,signNum,signTime,verifNum,verifTime] = l
                    viewSyncMsgs = "0"

                valTH = float(thru)
                throughputViewNum += 1
                throughputViewVal += valTH
                printNodePoint(protocol,numFaults,numJoiners,numDeadNodes,"throughput-view",valTH)

                valLA = float(lat)
                latencyViewNum += 1
                latencyViewVal += valLA
                printNodePoint(protocol,numFaults,numJoiners,numDeadNodes,"latency-view",valLA)

                valHD = float(hdl)
                handleNum += 1
                handleVal += valHD
                printNodePoint(protocol,numFaults,numJoiners,numDeadNodes,"handle",valHD)

                valTO = float(tos)
                tosNum += 1
                tosVal += valTO
                printNodePoint(protocol,numFaults,numJoiners,numDeadNodes,"timeouts",valTO)

                valPB = float(pbs)
                pbsNum += 1
                pbsVal += valPB
                printNodePoint(protocol,numFaults,numJoiners,numDeadNodes,"onepbs",valPB)

                valPC = float(pcs)
                pcsNum += 1
                pcsVal += valPC
                printNodePoint(protocol,numFaults,numJoiners,numDeadNodes,"onepcs",valPC)

                valVS = float(viewSyncMsgs)
                viewSyncMsgsNum += 1
                viewSyncMsgsVal += valVS
                printNodePoint(protocol,numFaults,numJoiners,numDeadNodes,"view-sync-msgs-per-view",valVS)

                valST = float(signTime)
                cryptoSignNum += 1
                cryptoSignVal += valST
                printNodePoint(protocol,numFaults,numJoiners,numDeadNodes,"crypto-sign",valST)

                valVT = float(verifTime)
                cryptoVerifNum += 1
                cryptoVerifVal += valVT
                printNodePoint(protocol,numFaults,numJoiners,numDeadNodes,"crypto-verif",valVT)

                valSN = int(signNum)
                cryptoNumSignNum += 1
                cryptoNumSignVal += valSN
                printNodePoint(protocol,numFaults,numJoiners,numDeadNodes,"crypto-num-sign",valSN)

                valVN = int(verifNum)
                cryptoNumVerifNum += 1
                cryptoNumVerifVal += valVN
                printNodePoint(protocol,numFaults,numJoiners,numDeadNodes,"crypto-num-verif",valVN)

    throughputView = throughputViewVal/throughputViewNum if throughputViewNum > 0 else 0.0
    latencyView    = latencyViewVal/latencyViewNum       if latencyViewNum > 0    else 0.0
    handle         = handleVal/handleNum                 if handleNum > 0         else 0.0
    timeouts       = tosVal/tosNum                       if tosNum > 0            else 0.0
    viewSyncMsgs   = viewSyncMsgsVal/viewSyncMsgsNum     if viewSyncMsgsNum > 0   else 0.0
    cryptoSign     = cryptoSignVal/cryptoSignNum         if cryptoSignNum > 0     else 0.0
    cryptoVerif    = cryptoVerifVal/cryptoVerifNum       if cryptoVerifNum > 0    else 0.0
    cryptoNumSign  = cryptoNumSignVal/cryptoNumSignNum   if cryptoNumSignNum > 0  else 0.0
    cryptoNumVerif = cryptoNumVerifVal/cryptoNumVerifNum if cryptoNumVerifNum > 0 else 0.0

    print("throughput-view:",  throughputView, "out of", throughputViewNum)
    print("latency-view:",     latencyView,    "out of", latencyViewNum)
    print("handle:",           handle,         "out of", handleNum)
    print("timeouts:",         timeouts,       "out of", tosNum)
    print("view-sync-msgs-per-view:", viewSyncMsgs, "out of", viewSyncMsgsNum)
    print("crypto-sign:",      cryptoSign,     "out of", cryptoSignNum)
    print("crypto-verif:",     cryptoVerif,    "out of", cryptoVerifNum)
    print("crypto-num-sign:",  cryptoNumSign,  "out of", cryptoNumSignNum)
    print("crypto-num-verif:", cryptoNumVerif, "out of", cryptoNumVerifNum)

    return (throughputView, latencyView, handle, timeouts, viewSyncMsgs, cryptoSign, cryptoVerif, cryptoNumSign, cryptoNumVerif)
## End of computeStats


def startContainers(numReps,numClients):
    print("running in docker mode, starting" , numReps, "containers for the replicas and", numClients, "for the clients")

    global ipsOfNodes

    lr = list(map(lambda x: (True, x, str(x)), list(range(numReps))))            # replicas
    lc = list(map(lambda x: (False, x, "c" + str(x)), list(range(numClients))))  # clients
    lall = lr + lc + [(False , 0, "x")]

    # Batch cleanup is much faster than sequential stop/rm per container.
    instances = list(map(lambda x: dockerBase + x[2], lall))
    if len(instances) > 0:
        subprocess.run([docker + " rm -f " + " ".join(instances)], shell=True)
    subprocess.run([docker + " network rm " + mybridge], shell=True)

    subprocess.run([docker + " network create --driver=bridge " + mybridge], shell=True)

    # The 'x' containers are used in particular when we require less cpu so that we can compile in full-cpu
    # containers and copy over the code, from the x instance that does not have the restriction, which is
    # used to compile, to the non-x instance that has the restrictions
    for (isRep, j, i) in lall:
        instance  = dockerBase + i
        # TODO: make sure to cover all the ports
        opt1  = "--expose=" + str(startRport+numReps) if isRep else ""
        opt2  = "--expose=" + str(startCport+numReps) if isRep else ""
        opt3  = "-p " + str(startRport + j) + ":" + str(startRport + j) + "/tcp" if isRep else ""
        opt4  = "-p " + str(startCport + j) + ":" + str(startCport + j) + "/tcp" if isRep else ""
        opt5  = "--network=\"" + mybridge + "\""
        opt6  = "--cap-add=NET_ADMIN"
        opt7  = "--name " + instance
        optm  = "--memory=" + str(dockerMem) + "m" if dockerMem > 0 else ""
        optc  = "--cpus=\"" + str(dockerCpu) + "\"" if dockerCpu > 0 else ""
        opts  = " ".join([opt1, opt2, opt3, opt4, opt5, opt6, opt7, optm, optc]) # with cpu/mem limitations
        if i == "x":
            opts = " ".join([opt1, opt2, opt3, opt4, opt5, opt6, opt7])          # without cpu/mem limitations
        # We start the Docker instance
        subprocess.run([docker + " run -td " + opts + " " + dockerBase], shell=True, check=True)
        subprocess.run([docker + " exec -t " + instance + " bash -c \"" + srcsgx + "; mkdir -p " + statsdir + "\""], shell=True, check=True)
        # Set the network latency
        if 0 < networkLat and i != "x":
            print("----changing network latency to " + str(networkLat) + "ms")
            rate = ""
            if rateMbit > 0:
                BUF_PKTS=33
                BDP_BYTES=(networkLat/1000.0)*(rateMbit*1000000.0/8.0)
                BDP_PKTS=BDP_BYTES/1500
                LIMIT_PKTS=BDP_PKTS+BUF_PKTS
                rate = " rate " + str(rateMbit) + "Mbit limit " + str(LIMIT_PKTS)
            #latcmd = "tc qdisc add dev eth0 root netem delay " + str(networkLat) + "ms " + str(networkVar) + "ms distribution normal" + rate
            # the distribution arg causes problems... the default distribution is normal anyway
            latcmd = "tc qdisc add dev eth0 root netem delay " + str(networkLat) + "ms " + str(networkVar) + "ms" + rate + " loss " + str(msgLoss) + "%"
            print(latcmd)
            #latcmd = "tc qdisc add dev eth0 root netem delay " + str(networkLat) + "ms"
            subprocess.run([docker + " exec -t " + instance + " bash -c \"" + latcmd + "\""], shell=True, check=True)
        # Only replicas need their IP in ipsOfNodes.
        if isRep:
            ipcmd = docker + " inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' " + instance
            out = subprocess.run(ipcmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True).stdout.strip()
            if out:
                print("----container's address:" + out)
                ipsOfNodes.update({int(i):out})
            else:
                print("----container's address: UNKNOWN")
## End of startContainers


def stopContainers(numReps,numClients):
    print("stopping and removing docker containers")

    lr = list(map(lambda x: (True, str(x)), list(range(numReps))))            # replicas
    lc = list(map(lambda x: (False, "c" + str(x)), list(range(numClients))))  # clients
    lall = lr + lc + [(False , "x")]

    instances = list(map(lambda x: dockerBase + x[1], lall))
    if len(instances) > 0:
        subprocess.run([docker + " rm -f " + " ".join(instances)], shell=True)

    subprocess.run([docker + " network rm " + mybridge], shell=True)
## End of stopContainers


# if 'recompile' is true, the application will be recompiled (default=true)
def computeAvgStats(recompile,
                    protocol,
                    constFactor,
                    numClTrans,
                    sleepTime,
                    numViews,
                    cutOffBound,
                    numFaults,
                    numJoiners,
                    numDeadNodes,
                    numRepeats):
    print("<<<<<<<<<<<<<<<<<<<<",
          "protocol="+protocol.value,
          ";regions="+regions[0],
          ";payload="+str(payloadSize),
          ";factor="+str(constFactor),
          ";#faults="+str(numFaults),
          ";#joiners="+str(numJoiners),
          ";#repeats="+str(numRepeats),
          "[complete-runs="+str(completeRuns),"aborted-runs="+str(abortedRuns)+"]")
    print("aborted runs so far:", aborted)

    g = open(timesFile, 'a')
    g.write("# "+protocol.value+" "+str(numFaults)+"\n")
    g.close()

    throughputViews = []
    latencyViews    = []
    handles         = []
    viewSyncs       = []
    cryptoSigns     = []
    cryptoVerifs    = []
    cryptoNumSigns  = []
    cryptoNumVerifs = []

    numReps = (constFactor * numFaults) + 1

    if runDocker:
        startContainers(numReps,numClients)

    # building App with correct parameters
    if recompile:
        mkApp(protocol,constFactor,numFaults,numTrans,payloadSize)

    goodValues = 0

    # running 'numRepeats' time
    for i in range(numRepeats):
        print(">>>>>>>>>>>>>>>>>>>>",
              "protocol="+protocol.value,
              ";regions="+regions[0],
              ";payload="+str(payloadSize),
              ";factor="+str(constFactor),
              ";#faults="+str(numFaults),
              ";#joiners="+str(numJoiners),
              ";repeat="+str(i),
              "[complete-runs="+str(completeRuns),"aborted-runs="+str(abortedRuns)+"]")
        print("aborted runs so far:", aborted)
        clearStatsDir()
        execute(protocol,constFactor,numClTrans,sleepTime,numViews,cutOffBound,numFaults,numDeadNodes,numJoiners,i)
        (throughputView,latencyView,handle,timeouts,viewSyncMsgs,cryptoSign,cryptoVerif,cryptoNumSign,cryptoNumVerif) = computeStats(protocol,numFaults,numJoiners,numDeadNodes,i,numRepeats)
        # Some protocols (e.g., OneShot variants) can legitimately report zero crypto metrics.
        # Keep repeats as long as core performance metrics are valid.
        if throughputView > 0 and latencyView > 0 and handle > 0:
            throughputViews.append(throughputView)
            latencyViews.append(latencyView)
            handles.append(handle)
            viewSyncs.append(viewSyncMsgs)
            cryptoSigns.append(cryptoSign)
            cryptoVerifs.append(cryptoVerif)
            cryptoNumSigns.append(cryptoNumSign)
            cryptoNumVerifs.append(cryptoNumVerif)
            goodValues += 1

    if runDocker:
        stopContainers(numReps,numClients)

    throughputView = sum(throughputViews)/goodValues if goodValues > 0 else 0.0
    latencyView    = sum(latencyViews)/goodValues    if goodValues > 0 else 0.0
    handle         = sum(handles)/goodValues         if goodValues > 0 else 0.0
    viewSyncMsgs   = sum(viewSyncs)/goodValues       if goodValues > 0 else 0.0
    cryptoSign     = sum(cryptoSigns)/goodValues     if goodValues > 0 else 0.0
    cryptoVerif    = sum(cryptoVerifs)/goodValues    if goodValues > 0 else 0.0
    cryptoNumSign  = sum(cryptoNumSigns)/goodValues  if goodValues > 0 else 0.0
    cryptoNumVerif = sum(cryptoNumVerifs)/goodValues if goodValues > 0 else 0.0

    print("avg throughput (view):",  throughputView)
    print("avg latency (view):",     latencyView)
    print("avg handle:",             handle)
    print("avg view-sync-msgs-per-view:", viewSyncMsgs)
    print("avg crypto (sign):",      cryptoSign)
    print("avg crypto (verif):",     cryptoVerif)
    print("avg crypto (sign-num):",  cryptoNumSign)
    print("avg crypto (verif-num):", cryptoNumVerif)

    return (throughputView, latencyView, handle, cryptoSign, cryptoVerif, cryptoNumSign, cryptoNumVerif)
# End of computeAvgStats


def dict2val(d,f):
    (v,n) = d.get(f)
    #print((v,n))
    return sum(v)/n


# p is a Boolean: true to print some debugging info
# q is a Boolean: true to generate averages
def dict2lists(d,quantileSize,p,q):
    keys = []
    vals = []
    nums = []

    # We create the lists of points from the dictionaries
    # 'val' is a list of 'num' reals
    for k,(val,num) in d.items():
        keys.append(k)
        val  = sorted(val)           # we sort the values
        l    = len(val)              # this should be num, the number of values we have in val
        n    = int(l/(100/quantileSize)) if quantileSize > 0 else 0 # we'll remove n values from the top and bottom
        newval = val[n:l-n]           # we're removing them
        #newval = val[n:l-n]          # we're removing them
        m    = len(newval)           # we're only keeping m values out of the l
        s    = sum(newval)           # we're summing up the values
        v    = s/m if m > 0 else 0.0 # and computing the average
        if p:
            print(l,quantileSize,n,v,m,"---------\n", val, "\n", newval,"\n")
        if q:
            vals.append(v)
        else:
            vals.append(newval)
        nums.append(m)

    return (keys,vals,nums)
# End of dict2lists


## So that 3f1+1=2f2+1
def comparisonN(f1,f2,dTVBase,dTVCheap,dTVQuick,dTVDamq,dTVComb,dTVDamr,dTVDama,dTVDamp,dTVChBase,dTVChComb,dLVBase,dLVCheap,dLVQuick,dLVDamq,dLVComb,dLVDamr,dLVDama,dLVDamp,dLVChBase,dLVChComb):
    tv1 = dict2val(dTVBase,f1)
    tv2 = dict2val(dTVCheap,f2)
    tv3 = dict2val(dTVQuick,f2)
    tv4 = dict2val(dTVComb,f2)
    tv5 = dict2val(dTVChBase,f1)
    tv6 = dict2val(dTVChComb,f2)
    tv7 = dict2val(dTVDamr,f2)
    #tv7 = dict2val(dTVDama,f2)
    tv8 = dict2val(dTVDamp,f2)
    tv9 = dict2val(dTVDamq,f2)

    tv12 = (tv2 - tv1) / tv1 * 100
    tv13 = (tv3 - tv1) / tv1 * 100
    tv14 = (tv4 - tv1) / tv1 * 100
    tv56 = (tv6 - tv5) / tv5 * 100
    print("THROUGHPUT","cheap",tv12,"quick",tv13,"comb",tv14,"chcomb",tv56)

    lv1 = dict2val(dLVBase,f1)
    lv2 = dict2val(dLVCheap,f2)
    lv3 = dict2val(dLVQuick,f2)
    lv4 = dict2val(dLVComb,f2)
    lv5 = dict2val(dLVChBase,f1)
    lv6 = dict2val(dLVChComb,f2)
    lv7 = dict2val(dLVDamr,f2)
    #lv7 = dict2val(dLVDama,f2)
    lv8 = dict2val(dLVDamp,f2)
    lv9 = dict2val(dLVDamq,f2)

    lv12 = (lv1 - lv2) / lv1 * 100
    lv13 = (lv1 - lv3) / lv1 * 100
    lv14 = (lv1 - lv4) / lv1 * 100
    lv56 = (lv5 - lv6) / lv5 * 100
    print("LATENCY","cheap",lv12,"quick",lv13,"comb",lv14,"chcomb",lv56)
## End of comparisonN


# 'bo' should be False for throughput (increase) and True for latency (decrease)
def getPercentage(bo,nameBase,faultsBase,valsBase,nameNew,faultsNew,valsNew):
    newTot = 0.0
    newMin = 0.0
    newMax = 0.0
    newLst = []

    if faultsBase == faultsNew:
        for (n,baseVal,newVal) in zip(faultsBase,valsBase,valsNew):
            #new = (a / b) * 100 if bo else (b / a) * 100
            #print((n,baseVal,newVal))
            new = (baseVal - newVal) / baseVal * 100 if bo else (newVal - baseVal) / baseVal * 100
            newTot += new

            if new > newMax: newMax = new
            if (new < newMin or newMin == 0.0): newMin = new
            newLst.append((n,new))

    newAvg = newTot / len(faultsBase) if len(faultsBase) > 0 else 0

    print(nameNew + "/" + nameBase + "(#faults/value): " + str(newLst))
    print(nameNew + "/" + nameBase + "(avg/min/ax): " + "avg=" + str(newAvg) + ";min=" + str(newMin) + ";max=" + str(newMax))
# End of getPercentage


# From: https://stackoverflow.com/questions/7965743/how-can-i-set-the-aspect-ratio-in-matplotlib
def adjustFigAspect(fig,aspect=1):
    '''
    Adjust the subplot parameters so that the figure has the correct
    aspect ratio.
    '''
    xsize,ysize = fig.get_size_inches()
    minsize = min(xsize,ysize)
    xlim = .4*minsize/xsize
    ylim = .4*minsize/ysize
    if aspect < 1:
        xlim *= aspect
    else:
        ylim /= aspect
    fig.subplots_adjust(left=.5-xlim,
                        right=.5+xlim,
                        bottom=.5-ylim,
                        top=.5+ylim)
# End of adjustFigAspect


def updateDictionary(key,pointVal,d):
    (val,num) = d.get(key,([],0))
    val.append(float(pointVal))
    d.update({key:(val,num+1)})


def updateDictionaries(protVal,numFaults,numJoins,numDeads,pointVal,dBase,dCheap,dQuick,dDamq,dComb,dDamr,dDama,dDamp,dFree,dRoll,dOnep,dOnepB,dOnepC,dOnepD,dChBase,dChComb):
    key = numFaults

    if deadNodes:
        key = numDeads

    if joining:
        key = numJoins

    if protVal == "BASIC_BASELINE":
        updateDictionary(key,pointVal,dBase)
    if protVal == "BASIC_CHEAP":
        updateDictionary(key,pointVal,dCheap)
    if protVal == "BASIC_QUICK":
        updateDictionary(key,pointVal,dQuick)
    if protVal == "BASIC_QUICK_DEBUG":
        updateDictionary(key,pointVal,dQuick)
    if protVal == "BASIC_FREE":
        updateDictionary(key,pointVal,dFree)
    if protVal == "BASIC_CHEAP_AND_QUICK":
        updateDictionary(key,pointVal,dComb)
    if protVal == "BASIC_DAMYSUS_ROTE":
        updateDictionary(key,pointVal,dDamr)
    if protVal == "BASIC_DAMYSUS_ACHILLES":
        updateDictionary(key,pointVal,dDama)
    if protVal == "BASIC_DAMYSUS_PACEMAKER":
        updateDictionary(key,pointVal,dDamp)
    if protVal == "BASIC_DAMYSUS3_PACEMAKER":
        updateDictionary(key,pointVal,dDamq)
    if protVal == "BASIC_ROLL":
        updateDictionary(key,pointVal,dRoll)
    if protVal == "BASIC_ONEP":
        updateDictionary(key,pointVal,dOnep)
    if protVal == "BASIC_ONEPB":
        updateDictionary(key,pointVal,dOnepB)
    if protVal == "BASIC_ONEPC":
        updateDictionary(key,pointVal,dOnepC)
    if protVal == "BASIC_ONEPD":
        updateDictionary(key,pointVal,dOnepD)
    if protVal == "CHAINED_BASELINE":
        updateDictionary(key,pointVal,dChBase)
    if protVal == "CHAINED_CHEAP_AND_QUICK":
        updateDictionary(key,pointVal,dChComb)
    if protVal == "CHAINED_CHEAP_AND_QUICK_DEBUG":
        updateDictionary(key,pointVal,dChComb)


def createPlot(pFile):
    # throughput-view
    dictTVBase   = {}
    dictTVCheap  = {}
    dictTVQuick  = {}
    dictTVDamq   = {}
    dictTVComb   = {}
    dictTVDamr   = {}
    dictTVDama   = {}
    dictTVDamp   = {}
    dictTVFree   = {}
    dictTVRoll   = {}
    dictTVOnep   = {}
    dictTVOnepB  = {}
    dictTVOnepC  = {}
    dictTVOnepD  = {}
    dictTVChBase = {}
    dictTVChComb = {}

    # latency-view
    dictLVBase   = {}
    dictLVCheap  = {}
    dictLVQuick  = {}
    dictLVDamq   = {}
    dictLVComb   = {}
    dictLVDamr   = {}
    dictLVDama   = {}
    dictLVDamp   = {}
    dictLVFree   = {}
    dictLVRoll   = {}
    dictLVOnep   = {}
    dictLVOnepB  = {}
    dictLVOnepC  = {}
    dictLVOnepD  = {}
    dictLVChBase = {}
    dictLVChComb = {}

    # handle
    dictHBase   = {}
    dictHCheap  = {}
    dictHQuick  = {}
    dictHDamq   = {}
    dictHComb   = {}
    dictHDamr   = {}
    dictHDama   = {}
    dictHDamp   = {}
    dictHFree   = {}
    dictHRoll   = {}
    dictHOnep   = {}
    dictHOnepB  = {}
    dictHOnepC  = {}
    dictHOnepD  = {}
    dictHChBase = {}
    dictHChComb = {}

    # timeouts
    dictTOBase   = {}
    dictTOCheap  = {}
    dictTOQuick  = {}
    dictTODamq   = {}
    dictTOComb   = {}
    dictTODamr   = {}
    dictTODama   = {}
    dictTODamp   = {}
    dictTOFree   = {}
    dictTORoll   = {}
    dictTOOnep   = {}
    dictTOOnepB  = {}
    dictTOOnepC  = {}
    dictTOOnepD  = {}
    dictTOChBase = {}
    dictTOChComb = {}

    # onepbs
    dictPBBase   = {}
    dictPBCheap  = {}
    dictPBQuick  = {}
    dictPBDamq   = {}
    dictPBComb   = {}
    dictPBDamr   = {}
    dictPBDama   = {}
    dictPBDamp   = {}
    dictPBFree   = {}
    dictPBRoll   = {}
    dictPBOnep   = {}
    dictPBOnepB  = {}
    dictPBOnepC  = {}
    dictPBOnepD  = {}
    dictPBChBase = {}
    dictPBChComb = {}

    # onepcs
    dictPCBase   = {}
    dictPCCheap  = {}
    dictPCQuick  = {}
    dictPCDamq   = {}
    dictPCComb   = {}
    dictPCDamr   = {}
    dictPCDama   = {}
    dictPCDamp   = {}
    dictPCFree   = {}
    dictPCRoll   = {}
    dictPCOnep   = {}
    dictPCOnepB  = {}
    dictPCOnepC  = {}
    dictPCOnepD  = {}
    dictPCChBase = {}
    dictPCChComb = {}

    # crypto-sign
    dictCSBase   = {}
    dictCSCheap  = {}
    dictCSQuick  = {}
    dictCSDamq   = {}
    dictCSComb   = {}
    dictCSDamr   = {}
    dictCSDama   = {}
    dictCSDamp   = {}
    dictCSFree   = {}
    dictCSRoll   = {}
    dictCSOnep   = {}
    dictCSOnepB  = {}
    dictCSOnepC  = {}
    dictCSOnepD  = {}
    dictCSChBase = {}
    dictCSChComb = {}

    # crypto-verif
    dictCVBase   = {}
    dictCVCheap  = {}
    dictCVQuick  = {}
    dictCVDamq   = {}
    dictCVComb   = {}
    dictCVDamr   = {}
    dictCVDama   = {}
    dictCVDamp   = {}
    dictCVFree   = {}
    dictCVRoll   = {}
    dictCVOnep   = {}
    dictCVOnepB  = {}
    dictCVOnepC  = {}
    dictCVOnepD  = {}
    dictCVChBase = {}
    dictCVChComb = {}

    global dockerCpu, dockerMem, networkLat, payloadSize, repeats, repeatsL2, numViews, rateMbit

    # We accumulate all the points in dictionaries
    print("reading points from:", pFile)
    f = open(pFile,'r')
    for line in f.readlines():
        if line.startswith("##params"):
            args = line.split(" ")
            cpu     = "cpus=0"
            mem     = "mem=0"
            lat     = "lat=0"
            rate    = "rate=0"
            payload = "payload=0"
            rep1    = "repeats1=0"
            rep2    = "repeats2=0"
            views   = "views=0"
            regs    = "regions=one"
            if len(args) == 9:
                [hdr,cpu,mem,lat,payload,rep1,rep2,views,regs] = args
            elif len(args) == 10:
                [hdr,cpu,mem,lat,rate,payload,rep1,rep2,views,regs] = args
            else:
                print("WRONG ARGUMENTS in ##params comment")
            [cpuTag,cpuVal] = cpu.split("=")
            dockerCpu = float(cpuVal)
            [memTag,memVal] = mem.split("=")
            dockerMem = int(memVal)
            [latTag,latVal] = lat.split("=")
            networkLat = float(latVal)
            [rateTag,rateVal] = rate.split("=")
            rateMbit = float(rateVal)
            [payloadTag,payloadVal] = payload.split("=")
            payloadSize = int(payloadVal)
            [rep1Tag,rep1Val] = rep1.split("=")
            repeats = int(rep1Val)
            [rep2Tag,rep2Val] = rep2.split("=")
            repeatsL2 = int(rep2Val)
            [viewsTag,viewsVal] = views.split("=")
            numViews = int(viewsVal)
            [regsTag,regsVal] = regs.split("=")
            setRegion(regsVal)

        if line.startswith("protocol"):
            l = line.split(" ")
            prot   = "protocol=BASIC_BASELINE"
            faults = "faults=1"
            joins  = "joiners=0"
            deads  = "deads=0"
            point  = "throughput-view=0.0"
            if len(l) == 3:
                [prot,faults,point] = l
            elif len(l) == 4:
                [prot,faults,deads,point] = l
            elif len(l) == 5:
                [prot,faults,joins,deads,point] = l
            else:
                print("WRONG ARGUMENTS in point line: " + line)
            [protTag,protVal]     = prot.split("=")
            [faultsTag,faultsVal] = faults.split("=")
            [joinsTag,joinsVal]   = joins.split("=")
            [deadsTag,deadsVal]   = deads.split("=")
            [pointTag,pointVal]   = point.split("=")
            numFaults=int(faultsVal)
            numJoins=int(joinsVal)
            numDeads=int(deadsVal)
            if float(pointVal) < float('inf'):
                # Throughputs-view
                if pointTag == "throughput-view":
                    updateDictionaries(protVal,numFaults,numJoins,numDeads,pointVal,dictTVBase,dictTVCheap,dictTVQuick,dictTVDamq,dictTVComb,dictTVDamr,dictTVDama,dictTVDamp,dictTVFree,dictTVRoll,dictTVOnep,dictTVOnepB,dictTVOnepC,dictTVOnepD,dictTVChBase,dictTVChComb)
                # Latencies-view
                if pointTag == "latency-view":
                    updateDictionaries(protVal,numFaults,numJoins,numDeads,pointVal,dictLVBase,dictLVCheap,dictLVQuick,dictLVDamq,dictLVComb,dictLVDamr,dictLVDama,dictLVDamp,dictLVFree,dictLVRoll,dictLVOnep,dictLVOnepB,dictLVOnepC,dictLVOnepD,dictLVChBase,dictLVChComb)
                # handle
                if (pointTag == "handle" or pointTag == "latency-handle"):
                    updateDictionaries(protVal,numFaults,numJoins,numDeads,pointVal,dictHBase,dictHCheap,dictHQuick,dictHDamq,dictHComb,dictHDamr,dictHDama,dictHDamp,dictHFree,dictHRoll,dictHOnep,dictHOnepB,dictHOnepC,dictHOnepD,dictHChBase,dictHChComb)
                # timeouts
                if pointTag == "timeouts":
                    updateDictionaries(protVal,numFaults,numJoins,numDeads,pointVal,dictTOBase,dictTOCheap,dictTOQuick,dictTODamq,dictTOComb,dictTODamr,dictTODama,dictTODamp,dictTOFree,dictTORoll,dictTOOnep,dictTOOnepB,dictTOOnepC,dictTOOnepD,dictTOChBase,dictTOChComb)
                # onepbs
                if pointTag == "onepbs":
                    updateDictionaries(protVal,numFaults,numJoins,numDeads,pointVal,dictPBBase,dictPBCheap,dictPBQuick,dictPBDamq,dictPBComb,dictPBDamr,dictPBDama,dictPBDamp,dictPBFree,dictPBRoll,dictPBOnep,dictPBOnepB,dictPBOnepC,dictPBOnepD,dictPBChBase,dictPBChComb)
                # onepcs
                if pointTag == "onepcs":
                    updateDictionaries(protVal,numFaults,numJoins,numDeads,pointVal,dictPCBase,dictPCCheap,dictPCQuick,dictPCDamq,dictPCComb,dictPCDamr,dictPCDama,dictPCDamp,dictPCFree,dictPCRoll,dictPCOnep,dictPCOnepB,dictPCOnepC,dictPCOnepD,dictPCChBase,dictPCChComb)
                # crypto-sign
                if pointTag == "crypto-sign":
                    updateDictionaries(protVal,numFaults,numJoins,numDeads,pointVal,dictCSBase,dictCSCheap,dictCSQuick,dictCSDamq,dictCSComb,dictCSDamr,dictCSDama,dictCSDamp,dictCSFree,dictCSRoll,dictCSOnep,dictCSOnepB,dictCSOnepC,dictCSOnepD,dictCSChBase,dictCSChComb)
                # crypto-verif
                if pointTag == "crypto-verif":
                    updateDictionaries(protVal,numFaults,numJoins,numDeads,pointVal,dictCVBase,dictCVCheap,dictCVQuick,dictCVDamq,dictCVComb,dictCVDamr,dictCVDama,dictCVDamp,dictCVFree,dictCVRoll,dictCVOnep,dictCVOnepB,dictCVOnepC,dictCVOnepD,dictCVChBase,dictCVChComb)
    f.close()

    quantileSize = 20
    quantileSize1 = 20
    quantileSize2 = 20

    # We convert the dictionaries to lists
    # throughput-view
    (faultsTVBase,   valsTVBase,   numsTVBase)   = dict2lists(dictTVBase,quantileSize,False,True)
    (faultsTVCheap,  valsTVCheap,  numsTVCheap)  = dict2lists(dictTVCheap,quantileSize,False,True)
    (faultsTVQuick,  valsTVQuick,  numsTVQuick)  = dict2lists(dictTVQuick,quantileSize,False,True)
    (faultsTVDamq,   valsTVDamq,   numsTVDamq)   = dict2lists(dictTVDamq,quantileSize,False,True)
    (faultsTVComb,   valsTVComb,   numsTVComb)   = dict2lists(dictTVComb,quantileSize,False,True)
    (faultsTVDamr,   valsTVDamr,   numsTVDamr)   = dict2lists(dictTVDamr,quantileSize,False,True)
    (faultsTVDama,   valsTVDama,   numsTVDama)   = dict2lists(dictTVDama,quantileSize,False,True)
    (faultsTVDamp,   valsTVDamp,   numsTVDamp)   = dict2lists(dictTVDamp,quantileSize,False,True)
    (faultsTVFree,   valsTVFree,   numsTVFree)   = dict2lists(dictTVFree,quantileSize,False,True)
    (faultsTVRoll,   valsTVRoll,   numsTVRoll)   = dict2lists(dictTVRoll,quantileSize,False,True)
    (faultsTVOnep,   valsTVOnep,   numsTVOnep)   = dict2lists(dictTVOnep,quantileSize,False,True)
    (faultsTVOnepB,  valsTVOnepB,  numsTVOnepB)  = dict2lists(dictTVOnepB,quantileSize,False,True)
    (faultsTVOnepC,  valsTVOnepC,  numsTVOnepC)  = dict2lists(dictTVOnepC,quantileSize,False,True)
    (faultsTVOnepD,  valsTVOnepD,  numsTVOnepD)  = dict2lists(dictTVOnepD,quantileSize,False,True)
    (faultsTVChBase, valsTVChBase, numsTVChBase) = dict2lists(dictTVChBase,quantileSize,False,True)
    (faultsTVChComb, valsTVChComb, numsTVChComb) = dict2lists(dictTVChComb,quantileSize,False,True)

    # latency-view
    (faultsLVBase,   valsLVBase,   numsLVBase)   = dict2lists(dictLVBase,quantileSize,False,True)
    (faultsLVCheap,  valsLVCheap,  numsLVCheap)  = dict2lists(dictLVCheap,quantileSize,False,True)
    (faultsLVQuick,  valsLVQuick,  numsLVQuick)  = dict2lists(dictLVQuick,quantileSize,False,True)
    (faultsLVDamq,   valsLVDamq,   numsLVDamq)   = dict2lists(dictLVDamq,quantileSize,False,True)
    (faultsLVComb,   valsLVComb,   numsLVComb)   = dict2lists(dictLVComb,quantileSize,False,True)
    (faultsLVDamr,   valsLVDamr,   numsLVDamr)   = dict2lists(dictLVDamr,quantileSize,False,True)
    (faultsLVDama,   valsLVDama,   numsLVDama)   = dict2lists(dictLVDama,quantileSize,False,True)
    (faultsLVDamp,   valsLVDamp,   numsLVDamp)   = dict2lists(dictLVDamp,quantileSize,False,True)
    (faultsLVFree,   valsLVFree,   numsLVFree)   = dict2lists(dictLVFree,quantileSize,False,True)
    (faultsLVRoll,   valsLVRoll,   numsLVRoll)   = dict2lists(dictLVRoll,quantileSize,False,True)
    (faultsLVOnep,   valsLVOnep,   numsLVOnep)   = dict2lists(dictLVOnep,quantileSize,False,True)
    (faultsLVOnepB,  valsLVOnepB,  numsLVOnepB)  = dict2lists(dictLVOnepB,quantileSize,False,True)
    (faultsLVOnepC,  valsLVOnepC,  numsLVOnepC)  = dict2lists(dictLVOnepC,quantileSize,False,True)
    (faultsLVOnepD,  valsLVOnepD,  numsLVOnepD)  = dict2lists(dictLVOnepD,quantileSize,False,True)
    (faultsLVChBase, valsLVChBase, numsLVChBase) = dict2lists(dictLVChBase,quantileSize,False,True)
    (faultsLVChComb, valsLVChComb, numsLVChComb) = dict2lists(dictLVChComb,quantileSize,False,True)

    # handle
    (faultsHBase,   valsHBase,   numsHBase)   = dict2lists(dictHBase,quantileSize1,False,True)
    (faultsHCheap,  valsHCheap,  numsHCheap)  = dict2lists(dictHCheap,quantileSize1,False,True)
    (faultsHQuick,  valsHQuick,  numsHQuick)  = dict2lists(dictHQuick,quantileSize1,False,True)
    (faultsHDamq,   valsHDamq,   numsHDamq)   = dict2lists(dictHDamq,quantileSize1,False,True)
    (faultsHComb,   valsHComb,   numsHComb)   = dict2lists(dictHComb,quantileSize1,False,True)
    (faultsHDamr,   valsHDamr,   numsHDamr)   = dict2lists(dictHDamr,quantileSize1,False,True)
    (faultsHDama,   valsHDama,   numsHDama)   = dict2lists(dictHDama,quantileSize1,False,True)
    (faultsHDamp,   valsHDamp,   numsHDamp)   = dict2lists(dictHDamp,quantileSize1,False,True)
    (faultsHFree,   valsHFree,   numsHFree)   = dict2lists(dictHFree,quantileSize1,False,True)
    (faultsHRoll,   valsHRoll,   numsHRoll)   = dict2lists(dictHRoll,quantileSize1,False,True)
    (faultsHOnep,   valsHOnep,   numsHOnep)   = dict2lists(dictHOnep,quantileSize1,False,True)
    (faultsHOnepB,  valsHOnepB,  numsHOnepB)  = dict2lists(dictHOnepB,quantileSize1,False,True)
    (faultsHOnepC,  valsHOnepC,  numsHOnepC)  = dict2lists(dictHOnepC,quantileSize1,False,True)
    (faultsHOnepD,  valsHOnepD,  numsHOnepD)  = dict2lists(dictHOnepD,quantileSize1,False,True)
    (faultsHChBase, valsHChBase, numsHChBase) = dict2lists(dictHChBase,quantileSize1,False,True)
    (faultsHChComb, valsHChComb, numsHChComb) = dict2lists(dictHChComb,quantileSize1,False,True)

    # timeouts
    (faultsTOBase,   valsTOBase,   numsTOBase)   = dict2lists(dictTOBase,0,False,True)
    (faultsTOCheap,  valsTOCheap,  numsTOCheap)  = dict2lists(dictTOCheap,0,False,True)
    (faultsTOQuick,  valsTOQuick,  numsTOQuick)  = dict2lists(dictTOQuick,0,False,True)
    (faultsTODamq,   valsTODamq,   numsTODamq)   = dict2lists(dictTODamq,0,False,True)
    (faultsTOComb,   valsTOComb,   numsTOComb)   = dict2lists(dictTOComb,0,False,True)
    (faultsTODamr,   valsTODamr,   numsTODamr)   = dict2lists(dictTODamr,0,False,True)
    (faultsTODama,   valsTODama,   numsTODama)   = dict2lists(dictTODama,0,False,True)
    (faultsTODamp,   valsTODamp,   numsTODamp)   = dict2lists(dictTODamp,0,False,True)
    (faultsTOFree,   valsTOFree,   numsTOFree)   = dict2lists(dictTOFree,0,False,True)
    (faultsTORoll,   valsTORoll,   numsTORoll)   = dict2lists(dictTORoll,0,False,True)
    (faultsTOOnep,   valsTOOnep,   numsTOOnep)   = dict2lists(dictTOOnep,0,False,True)
    (faultsTOOnepB,  valsTOOnepB,  numsTOOnepB)  = dict2lists(dictTOOnepB,0,False,True)
    (faultsTOOnepC,  valsTOOnepC,  numsTOOnepC)  = dict2lists(dictTOOnepC,0,False,True)
    (faultsTOOnepD,  valsTOOnepD,  numsTOOnepD)  = dict2lists(dictTOOnepD,0,False,True)
    (faultsTOChBase, valsTOChBase, numsTOChBase) = dict2lists(dictTOChBase,0,False,True)
    (faultsTOChComb, valsTOChComb, numsTOChComb) = dict2lists(dictTOChComb,0,False,True)

    # onepbs
    (faultsPBBase,   valsPBBase,   numsPBBase)   = dict2lists(dictPBBase,0,False,True)
    (faultsPBCheap,  valsPBCheap,  numsPBCheap)  = dict2lists(dictPBCheap,0,False,True)
    (faultsPBQuick,  valsPBQuick,  numsPBQuick)  = dict2lists(dictPBQuick,0,False,True)
    (faultsPBDamq,   valsPBDamq,   numsPBDamq)   = dict2lists(dictPBDamq,0,False,True)
    (faultsPBComb,   valsPBComb,   numsPBComb)   = dict2lists(dictPBComb,0,False,True)
    (faultsPBDamr,   valsPBDamr,   numsPBDamr)   = dict2lists(dictPBDamr,0,False,True)
    (faultsPBDama,   valsPBDama,   numsPBDama)   = dict2lists(dictPBDama,0,False,True)
    (faultsPBDamp,   valsPBDamp,   numsPBDamp)   = dict2lists(dictPBDamp,0,False,True)
    (faultsPBFree,   valsPBFree,   numsPBFree)   = dict2lists(dictPBFree,0,False,True)
    (faultsPBRoll,   valsPBRoll,   numsPBRoll)   = dict2lists(dictPBRoll,0,False,True)
    (faultsPBOnep,   valsPBOnep,   numsPBOnep)   = dict2lists(dictPBOnep,0,False,True)
    (faultsPBOnepB,  valsPBOnepB,  numsPBOnepB)  = dict2lists(dictPBOnepB,0,False,True)
    (faultsPBOnepC,  valsPBOnepC,  numsPBOnepC)  = dict2lists(dictPBOnepC,0,False,True)
    (faultsPBOnepD,  valsPBOnepD,  numsPBOnepD)  = dict2lists(dictPBOnepD,0,False,True)
    (faultsPBChBase, valsPBChBase, numsPBChBase) = dict2lists(dictPBChBase,0,False,True)
    (faultsPBChComb, valsPBChComb, numsPBChComb) = dict2lists(dictPBChComb,0,False,True)

    # onepcs
    (faultsPCBase,   valsPCBase,   numsPCBase)   = dict2lists(dictPCBase,0,False,True)
    (faultsPCCheap,  valsPCCheap,  numsPCCheap)  = dict2lists(dictPCCheap,0,False,True)
    (faultsPCQuick,  valsPCQuick,  numsPCQuick)  = dict2lists(dictPCQuick,0,False,True)
    (faultsPCDamq,   valsPCDamq,   numsPCDamq)   = dict2lists(dictPCDamq,0,False,True)
    (faultsPCComb,   valsPCComb,   numsPCComb)   = dict2lists(dictPCComb,0,False,True)
    (faultsPCDamr,   valsPCDamr,   numsPCDamr)   = dict2lists(dictPCDamr,0,False,True)
    (faultsPCDama,   valsPCDama,   numsPCDama)   = dict2lists(dictPCDama,0,False,True)
    (faultsPCDamp,   valsPCDamp,   numsPCDamp)   = dict2lists(dictPCDamp,0,False,True)
    (faultsPCFree,   valsPCFree,   numsPCFree)   = dict2lists(dictPCFree,0,False,True)
    (faultsPCRoll,   valsPCRoll,   numsPCRoll)   = dict2lists(dictPCRoll,0,False,True)
    (faultsPCOnep,   valsPCOnep,   numsPCOnep)   = dict2lists(dictPCOnep,0,False,True)
    (faultsPCOnepB,  valsPCOnepB,  numsPCOnepB)  = dict2lists(dictPCOnepB,0,False,True)
    (faultsPCOnepC,  valsPCOnepC,  numsPCOnepC)  = dict2lists(dictPCOnepC,0,False,True)
    (faultsPCOnepD,  valsPCOnepD,  numsPCOnepD)  = dict2lists(dictPCOnepD,0,False,True)
    (faultsPCChBase, valsPCChBase, numsPCChBase) = dict2lists(dictPCChBase,0,False,True)
    (faultsPCChComb, valsPCChComb, numsPCChComb) = dict2lists(dictPCChComb,0,False,True)

    # crypto-sign
    (faultsCSBase,   valsCSBase,   numsCSBase)   = dict2lists(dictCSBase,quantileSize2,False,True)
    (faultsCSCheap,  valsCSCheap,  numsCSCheap)  = dict2lists(dictCSCheap,quantileSize2,False,True)
    (faultsCSQuick,  valsCSQuick,  numsCSQuick)  = dict2lists(dictCSQuick,quantileSize2,False,True)
    (faultsCSDamq,   valsCSDamq,   numsCSDamq)   = dict2lists(dictCSDamq,quantileSize2,False,True)
    (faultsCSComb,   valsCSComb,   numsCSComb)   = dict2lists(dictCSComb,quantileSize2,False,True)
    (faultsCSDamr,   valsCSDamr,   numsCSDamr)   = dict2lists(dictCSDamr,quantileSize2,False,True)
    (faultsCSDama,   valsCSDama,   numsCSDama)   = dict2lists(dictCSDama,quantileSize2,False,True)
    (faultsCSDamp,   valsCSDamp,   numsCSDamp)   = dict2lists(dictCSDamp,quantileSize2,False,True)
    (faultsCSFree,   valsCSFree,   numsCSFree)   = dict2lists(dictCSFree,quantileSize2,False,True)
    (faultsCSRoll,   valsCSRoll,   numsCSRoll)   = dict2lists(dictCSRoll,quantileSize2,False,True)
    (faultsCSOnep,   valsCSOnep,   numsCSOnep)   = dict2lists(dictCSOnep,quantileSize2,False,True)
    (faultsCSOnepB,  valsCSOnepB,  numsCSOnepB)  = dict2lists(dictCSOnepB,quantileSize2,False,True)
    (faultsCSOnepC,  valsCSOnepC,  numsCSOnepC)  = dict2lists(dictCSOnepC,quantileSize2,False,True)
    (faultsCSOnepD,  valsCSOnepD,  numsCSOnepD)  = dict2lists(dictCSOnepD,quantileSize2,False,True)
    (faultsCSChBase, valsCSChBase, numsCSChBase) = dict2lists(dictCSChBase,quantileSize2,False,True)
    (faultsCSChComb, valsCSChComb, numsCSChComb) = dict2lists(dictCSChComb,quantileSize2,False,True)

    # crypto-verif
    (faultsCVBase,   valsCVBase,   numsCVBase)   = dict2lists(dictCVBase,quantileSize2,False,True)
    (faultsCVCheap,  valsCVCheap,  numsCVCheap)  = dict2lists(dictCVCheap,quantileSize2,False,True)
    (faultsCVQuick,  valsCVQuick,  numsCVQuick)  = dict2lists(dictCVQuick,quantileSize2,False,True)
    (faultsCVDamq,   valsCVDamq,   numsCVDamq)   = dict2lists(dictCVDamq,quantileSize2,False,True)
    (faultsCVComb,   valsCVComb,   numsCVComb)   = dict2lists(dictCVComb,quantileSize2,False,True)
    (faultsCVDamr,   valsCVDamr,   numsCVDamr)   = dict2lists(dictCVDamr,quantileSize2,False,True)
    (faultsCVDama,   valsCVDama,   numsCVDama)   = dict2lists(dictCVDama,quantileSize2,False,True)
    (faultsCVDamp,   valsCVDamp,   numsCVDamp)   = dict2lists(dictCVDamp,quantileSize2,False,True)
    (faultsCVFree,   valsCVFree,   numsCVFree)   = dict2lists(dictCVFree,quantileSize2,False,True)
    (faultsCVRoll,   valsCVRoll,   numsCVRoll)   = dict2lists(dictCVRoll,quantileSize2,False,True)
    (faultsCVOnep,   valsCVOnep,   numsCVOnep)   = dict2lists(dictCVOnep,quantileSize2,False,True)
    (faultsCVOnepB,  valsCVOnepB,  numsCVOnepB)  = dict2lists(dictCVOnepB,quantileSize2,False,True)
    (faultsCVOnepC,  valsCVOnepC,  numsCVOnepC)  = dict2lists(dictCVOnepC,quantileSize2,False,True)
    (faultsCVOnepD,  valsCVOnepD,  numsCVOnepD)  = dict2lists(dictCVOnepD,quantileSize2,False,True)
    (faultsCVChBase, valsCVChBase, numsCVChBase) = dict2lists(dictCVChBase,quantileSize2,False,True)
    (faultsCVChComb, valsCVChComb, numsCVChComb) = dict2lists(dictCVChComb,quantileSize2,False,True)

    print("== faults/throughputs(val+num)/latencies(val+num)/cypto-verif(val+num)/cypto-sign(val+num)")
    if len(faultsTVBase):
        print("base",   (faultsTVBase,   (valsTVBase,   numsTVBase),   (valsLVBase,   numsLVBase),   (valsCVBase,   numsCVBase),   (valsCSBase,   numsCSBase),    (valsTOBase,   numsTOBase)))
    if len(faultsTVCheap):
        print("cheap",  (faultsTVCheap,  (valsTVCheap,  numsTVCheap),  (valsLVCheap,  numsLVCheap),  (valsCVCheap,  numsCVCheap),  (valsCSCheap,  numsCSCheap),   (valsTOCheap,  numsTOCheap)))
    if len(faultsTVQuick):
        print("quick",  (faultsTVQuick,  (valsTVQuick,  numsTVQuick),  (valsLVQuick,  numsLVQuick),  (valsCVQuick,  numsCVQuick),  (valsCSQuick,  numsCSQuick),   (valsTOQuick,  numsTOQuick)))
    if len(faultsTVDamq):
        print("damq",   (faultsTVDamq,   (valsTVDamq,   numsTVDamq),   (valsLVDamq,   numsLVDamq),   (valsCVDamq,   numsCVDamq),   (valsCSDamq,   numsCSDamq),    (valsTODamq,   numsTODamq)))
    if len(faultsTVComb):
        print("comb",   (faultsTVComb,   (valsTVComb,   numsTVComb),   (valsLVComb,   numsLVComb),   (valsCVComb,   numsCVComb),   (valsCSComb,   numsCSComb),    (valsTOComb,   numsTOComb)))
    if len(faultsTVDamr):
        print("damr",   (faultsTVDamr,   (valsTVDamr,   numsTVDamr),   (valsLVDamr,   numsLVDamr),   (valsCVDamr,   numsCVDamr),   (valsCSDamr,   numsCSDamr),    (valsTODamr,   numsTODamr)))
    if len(faultsTVDama):
        print("dama",   (faultsTVDama,   (valsTVDama,   numsTVDama),   (valsLVDama,   numsLVDama),   (valsCVDama,   numsCVDama),   (valsCSDama,   numsCSDama),    (valsTODama,   numsTODama)))
    if len(faultsTVDamp):
        print("damp",   (faultsTVDamp,   (valsTVDamp,   numsTVDamp),   (valsLVDamp,   numsLVDamp),   (valsCVDamp,   numsCVDamp),   (valsCSDamp,   numsCSDamp),    (valsTODamp,   numsTODamp)))
    if len(faultsTVFree):
        print("free",   (faultsTVFree,   (valsTVFree,   numsTVFree),   (valsLVFree,   numsLVFree),   (valsCVFree,   numsCVFree),   (valsCSFree,   numsCSFree),    (valsTOFree,   numsTOFree)))
    if len(faultsTVRoll):
        print("roll",   (faultsTVRoll,   (valsTVRoll,   numsTVRoll),   (valsLVRoll,   numsLVRoll),   (valsCVRoll,   numsCVRoll),   (valsCSRoll,   numsCSRoll),    (valsTORoll,   numsTORoll)))
    if len(faultsTVOnep):
        print("onep",   (faultsTVOnep,   (valsTVOnep,   numsTVOnep),   (valsLVOnep,   numsLVOnep),   (valsCVOnep,   numsCVOnep),   (valsCSOnep,   numsCSOnep),    (valsTOOnep,   numsTOOnep), (valsPBOnep, numsPBOnep), (valsPCOnep, numsPCOnep)))
    if len(faultsTVOnepB):
        print("onepb",  (faultsTVOnepB,  (valsTVOnepB,  numsTVOnepB),  (valsLVOnepB,  numsLVOnepB),  (valsCVOnepB,  numsCVOnepB),  (valsCSOnepB,  numsCSOnepB),   (valsTOOnepB,  numsTOOnepB)))
    if len(faultsTVOnepC):
        print("onepc",  (faultsTVOnepC,  (valsTVOnepC,  numsTVOnepC),  (valsLVOnepC,  numsLVOnepC),  (valsCVOnepC,  numsCVOnepC),  (valsCSOnepC,  numsCSOnepC),   (valsTOOnepC,  numsTOOnepC)))
    if len(faultsTVOnepD):
        print("onepd",  (faultsTVOnepD,  (valsTVOnepD,  numsTVOnepD),  (valsLVOnepD,  numsLVOnepD),  (valsCVOnepD,  numsCVOnepD),  (valsCSOnepD,  numsCSOnepD),   (valsTOOnepD,  numsTOOnepD)))
    if len(faultsTVChBase):
        print("chbase", (faultsTVChBase, (valsTVChBase, numsTVChBase), (valsLVChBase, numsLVChBase), (valsCVChBase, numsCVChBase), (valsCSChBase, numsCSChBase),  (valsTOChBase, numsTOChBase)))
    if len(faultsTVChComb):
        print("chcomb", (faultsTVChComb, (valsTVChComb, numsTVChComb), (valsLVChComb, numsLVChComb), (valsCVChComb, numsCVChComb), (valsCSChComb, numsCSChComb),  (valsTOChComb, numsTOChComb)))

    print("== faults/throughputs(val)/latencies(val)")
    if len(faultsTVBase):
        print("base",   faultsTVBase,   valsTVBase,   valsLVBase)
    if len(faultsTVCheap):
        print("cheap",  faultsTVCheap,  valsTVCheap,  valsLVCheap)
    if len(faultsTVQuick):
        print("quick",  faultsTVQuick,  valsTVQuick,  valsLVQuick)
    if len(faultsTVDamq):
        print("damq",   faultsTVDamq,   valsTVDamq,   valsLVDamq)
    if len(faultsTVComb):
        print("comb",   faultsTVComb,   valsTVComb,   valsLVComb)
    if len(faultsTVDamr):
        print("damr",   faultsTVDamr,   valsTVDamr,   valsLVDamr)
    if len(faultsTVDama):
        print("dama",   faultsTVDama,   valsTVDama,   valsLVDama)
    if len(faultsTVDamp):
        print("damp",   faultsTVDamp,   valsTVDamp,   valsLVDamp)
    if len(faultsTVFree):
        print("free",   faultsTVFree,   valsTVFree,   valsLVFree)
    if len(faultsTVRoll):
        print("roll",   faultsTVRoll,   valsTVRoll,   valsLVRoll)
    if len(faultsTVOnep):
        print("onep",   faultsTVOnep,   valsTVOnep,   valsLVOnep)
    if len(faultsTVOnepB):
        print("onepb",  faultsTVOnepB,  valsTVOnepB,  valsLVOnepB)
    if len(faultsTVOnepC):
        print("onepc",  faultsTVOnepC,  valsTVOnepC,  valsLVOnepC)
    if len(faultsTVOnepD):
        print("onepd",  faultsTVOnepD,  valsTVOnepD,  valsLVOnepD)
    if len(faultsTVChBase):
        print("chbase", faultsTVChBase, valsTVChBase, valsLVChBase)
    if len(faultsTVChComb):
        print("chcomb", faultsTVChComb, valsTVChComb, valsLVChComb)

    print("== Throughput gain (basic versions):")
    # non-chained
    if len(faultsTVCheap):
        getPercentage(False,baseHS,faultsTVBase,valsTVBase,cheapHS,faultsTVCheap,valsTVCheap)
    if len(faultsTVQuick):
        getPercentage(False,baseHS,faultsTVBase,valsTVBase,quickHS,faultsTVQuick,valsTVQuick)
    if len(faultsTVDamq):
        getPercentage(False,baseHS,faultsTVBase,valsTVBase,damqHS,faultsTVDamq,valsTVDamq)
    if len(faultsTVComb):
        getPercentage(False,baseHS,faultsTVBase,valsTVBase,combHS, faultsTVComb, valsTVComb)
    if len(faultsTVDamr):
        getPercentage(False,baseHS,faultsTVBase,valsTVBase,damrHS, faultsTVDamr, valsTVDamr)
    if len(faultsTVDama):
        getPercentage(False,baseHS,faultsTVBase,valsTVBase,damaHS, faultsTVDama, valsTVDama)
    if len(faultsTVDamp):
        getPercentage(False,baseHS,faultsTVBase,valsTVBase,dampHS, faultsTVDamp, valsTVDamp)
    if len(faultsTVFree):
        getPercentage(False,baseHS,faultsTVBase,valsTVBase,freeHS, faultsTVFree, valsTVFree)
    if len(faultsTVFree):
        getPercentage(False,combHS,faultsTVComb,valsTVComb,freeHS, faultsTVFree, valsTVFree)
    if len(faultsTVOnep):
        getPercentage(False,baseHS,faultsTVBase,valsTVBase,onepHS, faultsTVOnep, valsTVOnep)
    if len(faultsTVOnep):
        getPercentage(False,combHS,faultsTVComb,valsTVComb,onepHS, faultsTVOnep, valsTVOnep)
    if len(faultsTVRoll):
        getPercentage(False,damrHS,faultsTVDamr,valsTVDamr,rollHS, faultsTVRoll, valsTVRoll)
    if len(faultsTVRoll):
        getPercentage(False,damqHS,faultsTVDamq,valsTVDamq,rollHS, faultsTVRoll, valsTVRoll)
    # chained
    if len(faultsTVChComb):
        getPercentage(False,baseChHS,faultsTVChBase,valsTVChBase,combChHS,faultsTVChComb,valsTVChComb)

    print("== Latency gain (basic versions):")
    # non-chained
    if len(faultsLVCheap):
        getPercentage(True,baseHS,faultsLVBase,valsLVBase,cheapHS,faultsLVCheap,valsLVCheap)
    if len(faultsLVQuick):
        getPercentage(True,baseHS,faultsLVBase,valsLVBase,quickHS,faultsLVQuick,valsLVQuick)
    if len(faultsLVDamq):
        getPercentage(True,baseHS,faultsLVBase,valsLVBase,damqHS,faultsLVDamq,valsLVDamq)
    if len(faultsLVComb):
        getPercentage(True,baseHS,faultsLVBase,valsLVBase,combHS, faultsLVComb, valsLVComb)
    if len(faultsLVDamr):
        getPercentage(True,baseHS,faultsLVBase,valsLVBase,damrHS, faultsLVDamr, valsLVDamr)
    if len(faultsLVDama):
        getPercentage(True,baseHS,faultsLVBase,valsLVBase,damaHS, faultsLVDama, valsLVDama)
    if len(faultsLVDamp):
        getPercentage(True,baseHS,faultsLVBase,valsLVBase,dampHS, faultsLVDamp, valsLVDamp)
    if len(faultsLVFree):
        getPercentage(True,baseHS,faultsLVBase,valsLVBase,freeHS, faultsLVFree, valsLVFree)
    if len(faultsLVFree):
        getPercentage(True,combHS,faultsLVComb,valsLVComb,freeHS, faultsLVFree, valsLVFree)
    if len(faultsLVOnep):
        getPercentage(True,baseHS,faultsLVBase,valsLVBase,onepHS, faultsLVOnep, valsLVOnep)
    if len(faultsLVOnep):
        getPercentage(True,combHS,faultsLVComb,valsLVComb,onepHS, faultsLVOnep, valsLVOnep)
    if len(faultsLVRoll):
        getPercentage(True,damrHS,faultsLVDamr,valsLVDamr,rollHS, faultsLVRoll, valsLVRoll)
    if len(faultsLVRoll):
        getPercentage(True,damqHS,faultsLVDamq,valsLVDamq,rollHS, faultsLVRoll, valsLVRoll)
    # chained
    if len(faultsLVChComb):
        getPercentage(True,baseChHS,faultsLVChBase,valsLVChBase,combChHS,faultsLVChComb,valsLVChComb)

    print("== Handle gain (basic versions):")
    # non-chained
    if len(faultsHCheap):
        getPercentage(True,baseHS,faultsHBase,valsHBase,cheapHS,faultsHCheap,valsHCheap)
    if len(faultsHQuick):
        getPercentage(True,baseHS,faultsHBase,valsHBase,quickHS,faultsHQuick,valsHQuick)
    if len(faultsHDamq):
        getPercentage(True,baseHS,faultsHBase,valsHBase,damqHS,faultsHDamq,valsHDamq)
    if len(faultsHComb):
        getPercentage(True,baseHS,faultsHBase,valsHBase,combHS, faultsHComb, valsHComb)
    if len(faultsHDamr):
        getPercentage(True,baseHS,faultsHBase,valsHBase,damrHS, faultsHDamr, valsHDamr)
    if len(faultsHDama):
        getPercentage(True,baseHS,faultsHBase,valsHBase,damaHS, faultsHDama, valsHDama)
    if len(faultsHDamp):
        getPercentage(True,baseHS,faultsHBase,valsHBase,dampHS, faultsHDamp, valsHDamp)
    if len(faultsHFree):
        getPercentage(True,baseHS,faultsHBase,valsHBase,freeHS, faultsHFree, valsHFree)
    if len(faultsHFree):
        getPercentage(True,combHS,faultsHComb,valsHComb,freeHS, faultsHFree, valsHFree)
    if len(faultsHOnep):
        getPercentage(True,baseHS,faultsHBase,valsHBase,onepHS, faultsHOnep, valsHOnep)
    if len(faultsHOnep):
        getPercentage(True,combHS,faultsHComb,valsHComb,onepHS, faultsHOnep, valsHOnep)
    # chained
    if len(faultsHChComb):
        getPercentage(True,baseChHS,faultsHChBase,valsHChBase,combChHS,faultsHChComb,valsHChComb)

    LW = 1 # linewidth
    MS = 5 # markersize
    XYT = (0,5)

    #plt.figure(figsize=(2, 6))
    #, dpi=80)

    global plotThroughput
    global plotLatency

    if (plotHandle or plotCrypto) and not plotView:
        plotThroughput = False
        plotLatency    = True

    numPlots=2
    if (plotThroughput and not plotLatency) or (not plotThroughput and plotLatency):
        numPlots=1

    ## Plotting
    print("plotting",numPlots,"plot(s)")
    fig, axs = plt.subplots(numPlots,1)
    if numPlots == 1:
        x = axs
        axs = [x]
    #,figsize=(4, 10)
    if showTitle:
        if debugPlot:
            info = "file="+pFile
            info += "; cpus="+str(dockerCpu)
            info += "; mem="+str(dockerMem)
            info += "; lat="+str(networkLat)
            info += "; payload="+str(payloadSize)
            info += "; repeats1="+str(repeats)
            info += "; repeats2="+str(repeatsL2)
            info += "; #views="+str(numViews)
            info += "; regions="+regions[0]
            if plotHandle and not plotView:
                fig.suptitle("Handling time\n("+info+")")
            else:
                fig.suptitle("Throughputs (top) & Latencies (bottom)\n("+info+")")
        else:
            if plotHandle and not plotView:
                fig.suptitle("Handling time")
#            else:
#                fig.suptitle("Throughputs (top) & Latencies (bottom)")

    adjustFigAspect(fig,aspect=0.9)
    #adjustFigAspect(fig,aspect=0.9)
    if numPlots == 2:
        fig.set_figheight(6)
    else: # == 1
        fig.set_figheight(3)
    #fig.set_figwidth(4)

    if plotThroughput:
        xs = []
        # naming the x/y axis
        #axs[0].set(xlabel="#faults", ylabel="throughput")
        if showYlabel:
            axs[0].set(ylabel="throughput (Kops/s)")
        if logScale:
            axs[0].set_yscale('log')
        if whichExp == "EUexp1":
            axs[0].set_yticks((0.5,1,10,20,70))
            axs[0].set_ylim([0.5,70])
            axs[0].get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        elif whichExp == "ALLexp1":
            axs[0].set_yticks((0.3,1,6))
            axs[0].set_ylim([0.3,6])
            axs[0].get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        # giving a title to my graph
        #axs[0].set_title("throughputs")
        # plotting the points
        if plotView:
            if plotBasic:
                if len(faultsTVBase) > 0:
                    axs[0].plot(faultsTVBase,   valsTVBase,   color=baseCOL,   linewidth=LW, marker=baseMRK,   markersize=MS, linestyle=baseLS,   label=baseHS)
                    xs = list(set(xs) | set(faultsTVBase))
                if len(faultsTVCheap) > 0:
                    axs[0].plot(faultsTVCheap,  valsTVCheap,  color=cheapCOL,  linewidth=LW, marker=cheapMRK,  markersize=MS, linestyle=cheapLS,  label=cheapHS)
                    xs = list(set(xs) | set(faultsTVCheap))
                if len(faultsTVQuick) > 0:
                    axs[0].plot(faultsTVQuick,  valsTVQuick,  color=quickCOL,  linewidth=LW, marker=quickMRK,  markersize=MS, linestyle=quickLS,  label=quickHS)
                    xs = list(set(xs) | set(faultsTVQuick))
                if len(faultsTVDamq) > 0:
                    axs[0].plot(faultsTVDamq,   valsTVDamq,   color=damqCOL,   linewidth=LW, marker=damqMRK,   markersize=MS, linestyle=damqLS,   label=damqHS)
                    xs = list(set(xs) | set(faultsTVDamq))
                if plotComb and len(faultsTVComb) > 0:
                    axs[0].plot(faultsTVComb,   valsTVComb,   color=combCOL,   linewidth=LW, marker=combMRK,   markersize=MS, linestyle=combLS,   label=combHS)
                    xs = list(set(xs) | set(faultsTVComb))
                if len(faultsTVDamr) > 0:
                    axs[0].plot(faultsTVDamr,   valsTVDamr,   color=damrCOL,   linewidth=LW, marker=damrMRK,   markersize=MS, linestyle=damrLS,   label=damrHS)
                    xs = list(set(xs) | set(faultsTVDamr))
                if len(faultsTVDama) > 0:
                    axs[0].plot(faultsTVDama,   valsTVDama,   color=damaCOL,   linewidth=LW, marker=damaMRK,   markersize=MS, linestyle=damaLS,   label=damaHS)
                    xs = list(set(xs) | set(faultsTVDama))
                if len(faultsTVDamp) > 0:
                    axs[0].plot(faultsTVDamp,   valsTVDamp,   color=dampCOL,   linewidth=LW, marker=dampMRK,   markersize=MS, linestyle=dampLS,   label=dampHS)
                    xs = list(set(xs) | set(faultsTVDamp))
                if len(faultsTVFree) > 0:
                    axs[0].plot(faultsTVFree,   valsTVFree,   color=freeCOL,   linewidth=LW, marker=freeMRK,   markersize=MS, linestyle=freeLS,   label=freeHS)
                    xs = list(set(xs) | set(faultsTVFree))
                if len(faultsTVRoll) > 0:
                    axs[0].plot(faultsTVRoll,   valsTVRoll,   color=rollCOL,   linewidth=LW, marker=rollMRK,   markersize=MS, linestyle=rollLS,   label=rollHS)
                    xs = list(set(xs) | set(faultsTVRoll))
                if len(faultsTVOnep) > 0:
                    axs[0].plot(faultsTVOnep,   valsTVOnep,   color=onepCOL,   linewidth=LW, marker=onepMRK,   markersize=MS, linestyle=onepLS,   label=onepHS)
                    xs = list(set(xs) | set(faultsTVOnep))
                if len(faultsTVOnepB) > 0:
                    axs[0].plot(faultsTVOnepB,  valsTVOnepB,  color=onepbCOL,  linewidth=LW, marker=onepbMRK,  markersize=MS, linestyle=onepbLS,  label=onepbHS)
                    xs = list(set(xs) | set(faultsTVOnepB))
                if len(faultsTVOnepC) > 0:
                    axs[0].plot(faultsTVOnepC,  valsTVOnepC,  color=onepcCOL,  linewidth=LW, marker=onepcMRK,  markersize=MS, linestyle=onepcLS,  label=onepcHS)
                    xs = list(set(xs) | set(faultsTVOnepC))
                if len(faultsTVOnepD) > 0:
                    axs[0].plot(faultsTVOnepD,  valsTVOnepD,  color=onepdCOL,  linewidth=LW, marker=onepdMRK,  markersize=MS, linestyle=onepdLS,  label=onepdHS)
                    xs = list(set(xs) | set(faultsTVOnepD))
            if plotChained:
                if len(faultsTVChBase) > 0:
                    axs[0].plot(faultsTVChBase, valsTVChBase, color=baseChCOL, linewidth=LW, marker=baseChMRK, markersize=MS, linestyle=baseChLS, label=baseChHS)
                    xs = list(set(xs) | set(faultsTVChBase))
                if len(faultsTVChComb) > 0:
                    axs[0].plot(faultsTVChComb, valsTVChComb, color=combChCOL, linewidth=LW, marker=combChMRK, markersize=MS, linestyle=combChLS, label=combChHS)
                    xs = list(set(xs) | set(faultsTVChComb))
            if debugPlot:
                if plotBasic:
                    for x,y,z in zip(faultsTVBase, valsTVBase, numsTVBase):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsTVCheap, valsTVCheap, numsTVCheap):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsTVQuick, valsTVQuick, numsTVQuick):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsTVDamq, valsTVDamq, numsTVDamq):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsTVComb, valsTVComb, numsTVComb):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsTVDamr, valsTVDamr, numsTVDamr):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsTVDama, valsTVDama, numsTVDama):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsTVDamp, valsTVDamp, numsTVDamp):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsTVFree, valsTVFree, numsTVFree):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsTVRoll, valsTVRoll, numsTVRoll):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsTVOnep, valsTVOnep, numsTVOnep):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsTVOnepB, valsTVOnepB, numsTVOnepB):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsTVOnepC, valsTVOnepC, numsTVOnepC):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsTVOnepD, valsTVOnepD, numsTVOnepD):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                if plotChained:
                    for x,y,z in zip(faultsTVChBase, valsTVChBase, numsTVChBase):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsTVChComb, valsTVChComb, numsTVChComb):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')

        axs[0].set_xticks(xs)

        # legend
        if showLegend1:
            #axs[0].legend(ncol=1,prop={'size': 9},loc='upper center', bbox_to_anchor=(0.4, 1.44))
            axs[0].legend(ncol=1,prop={'size': 9})

    if plotLatency:
        xs = []
        ax=axs[0]
        if plotThroughput:
            ax=axs[1]
        # naming the x/y axis
        if showYlabel:
            if plotHandle and not plotView:
                if deadNodes:
                    ax.set(xlabel="#nodes", ylabel="handling time (ms)")
                else:
                    ax.set(xlabel="fault threshold (f)", ylabel="handling time (ms)")
            else:
                if deadNodes:
                    ax.set(xlabel="#nodes", ylabel="latency (ms)")
                else:
                    ax.set(xlabel="fault threshold (f)", ylabel="latency (ms)")
        else:
            ax.set(xlabel="fault threshold (f)")
        if logScale:
            ax.set_yscale('log')
        if whichExp == "EUexp1":
            ax.set_yticks((5,100,600))
            ax.set_ylim([5,600])
            ax.get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        elif whichExp == "ALLexp1":
            ax.set_yticks((60,100,1000))
            ax.set_ylim([60,1000])
            ax.get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        # giving a title to my graph
        #ax.set_title("latencies")
        # plotting the points
        if plotView:
            if plotBasic:
                if len(faultsLVBase) > 0: #and not runBase:
                    ax.plot(faultsLVBase,   valsLVBase,   color=baseCOL,   linewidth=LW, marker=baseMRK,   markersize=MS, linestyle=baseLS,   label=baseHS)
                    xs = list(set(xs) | set(faultsLVBase))
                if len(faultsLVCheap) > 0: #and not runCheap:
                    ax.plot(faultsLVCheap,  valsLVCheap,  color=cheapCOL,  linewidth=LW, marker=cheapMRK,  markersize=MS, linestyle=cheapLS,  label=cheapHS)
                    xs = list(set(xs) | set(faultsLVCheap))
                if len(faultsLVQuick) > 0: #and not runQuick:
                    ax.plot(faultsLVQuick,  valsLVQuick,  color=quickCOL,  linewidth=LW, marker=quickMRK,  markersize=MS, linestyle=quickLS,  label=quickHS)
                    xs = list(set(xs) | set(faultsLVQuick))
                if len(faultsLVDamq) > 0: #and not runDamq:
                    ax.plot(faultsLVDamq,   valsLVDamq,   color=damqCOL,   linewidth=LW, marker=damqMRK,   markersize=MS, linestyle=damqLS,   label=damqHS)
                    xs = list(set(xs) | set(faultsLVDamq))
                if plotComb and len(faultsLVComb) > 0: #and not runComb:
                    ax.plot(faultsLVComb,   valsLVComb,   color=combCOL,   linewidth=LW, marker=combMRK,   markersize=MS, linestyle=combLS,   label=combHS)
                    xs = list(set(xs) | set(faultsLVComb))
                if len(faultsLVDamr) > 0: #and not runDamr:
                    ax.plot(faultsLVDamr,   valsLVDamr,   color=damrCOL,   linewidth=LW, marker=damrMRK,   markersize=MS, linestyle=damrLS,   label=damrHS)
                    xs = list(set(xs) | set(faultsLVDamr))
                if len(faultsLVDama) > 0: #and not runDama:
                    ax.plot(faultsLVDama,   valsLVDama,   color=damaCOL,   linewidth=LW, marker=damaMRK,   markersize=MS, linestyle=damaLS,   label=damaHS)
                    xs = list(set(xs) | set(faultsLVDama))
                if len(faultsLVDamp) > 0: #and not runDamp:
                    ax.plot(faultsLVDamp,   valsLVDamp,   color=dampCOL,   linewidth=LW, marker=dampMRK,   markersize=MS, linestyle=dampLS,   label=dampHS)
                    xs = list(set(xs) | set(faultsLVDamp))
                if len(faultsLVFree) > 0: #and not runFree:
                    ax.plot(faultsLVFree,   valsLVFree,   color=freeCOL,   linewidth=LW, marker=freeMRK,   markersize=MS, linestyle=freeLS,   label=freeHS)
                    xs = list(set(xs) | set(faultsLVFree))
                if len(faultsLVRoll) > 0: #and not runRoll:
                    ax.plot(faultsLVRoll,   valsLVRoll,   color=rollCOL,   linewidth=LW, marker=rollMRK,   markersize=MS, linestyle=rollLS,   label=rollHS)
                    xs = list(set(xs) | set(faultsLVRoll))
                if len(faultsLVOnep) > 0: #and not runOnep:
                    ax.plot(faultsLVOnep,   valsLVOnep,   color=onepCOL,   linewidth=LW, marker=onepMRK,   markersize=MS, linestyle=onepLS,   label=onepHS)
                    xs = list(set(xs) | set(faultsLVOnep))
                if len(faultsLVOnepB) > 0: #and not runOnepB:
                    ax.plot(faultsLVOnepB,  valsLVOnepB,  color=onepbCOL,  linewidth=LW, marker=onepbMRK,  markersize=MS, linestyle=onepbLS,  label=onepbHS)
                    xs = list(set(xs) | set(faultsLVOnepB))
                if len(faultsLVOnepC) > 0: #and not runOnepC:
                    ax.plot(faultsLVOnepC,  valsLVOnepC,  color=onepcCOL,  linewidth=LW, marker=onepcMRK,  markersize=MS, linestyle=onepcLS,  label=onepcHS)
                    xs = list(set(xs) | set(faultsLVOnepC))
                if len(faultsLVOnepD) > 0: #and not runOnepD:
                    ax.plot(faultsLVOnepD,  valsLVOnepD,  color=onepdCOL,  linewidth=LW, marker=onepdMRK,  markersize=MS, linestyle=onepdLS,  label=onepdHS)
                    xs = list(set(xs) | set(faultsLVOnepD))
            if plotChained:
                if len(faultsLVChBase) > 0:
                    ax.plot(faultsLVChBase, valsLVChBase, color=baseChCOL, linewidth=LW, marker=baseChMRK, markersize=MS, linestyle=baseChLS, label=baseChHS)
                    xs = list(set(xs) | set(faultsLVChBase))
                if len(faultsLVChComb) > 0:
                    ax.plot(faultsLVChComb, valsLVChComb, color=combChCOL, linewidth=LW, marker=combChMRK, markersize=MS, linestyle=combChLS, label=combChHS)
                    xs = list(set(xs) | set(faultsLVChComb))
            if debugPlot:
                if plotBasic:
                    for x,y,z in zip(faultsLVBase, valsLVBase, numsLVBase):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsLVCheap, valsLVCheap, numsLVCheap):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsLVQuick, valsLVQuick, numsLVQuick):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsLVDamq, valsLVDamq, numsLVDamq):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsLVComb, valsLVComb, numsLVComb):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsLVDamr, valsLVDamr, numsLVDamr):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsLVDama, valsLVDama, numsLVDama):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsLVDamp, valsLVDamp, numsLVDamp):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsLVFree, valsLVFree, numsLVFree):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsLVRoll, valsLVRoll, numsLVRoll):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsLVOnep, valsLVOnep, numsLVOnep):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsLVOnepB, valsLVOnepB, numsLVOnepB):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsLVOnepC, valsLVOnepC, numsLVOnepC):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsLVOnepD, valsLVOnepD, numsLVOnepD):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                if plotChained:
                    for x,y,z in zip(faultsLVChBase, valsLVChBase, numsLVChBase):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsLVChComb, valsLVChComb, numsLVChComb):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
        if plotHandle:
            if plotBasic:
                if len(faultsHBase) > 0:
                    ax.plot(faultsHBase,   valsHBase,   color=baseCOL,   linewidth=LW, marker="+", markersize=MS, linestyle=baseLS,   label=baseHS+"")
                if len(faultsHCheap) > 0:
                    ax.plot(faultsHCheap,  valsHCheap,  color=cheapCOL,  linewidth=LW, marker="+", markersize=MS, linestyle=cheapLS,  label=cheapHS+"")
                if len(faultsHQuick) > 0:
                    ax.plot(faultsHQuick,  valsHQuick,  color=quickCOL,  linewidth=LW, marker="+", markersize=MS, linestyle=quickLS,  label=quickHS+"")
                if len(faultsHDamq) > 0:
                    ax.plot(faultsHDamq,   valsHDamq,   color=damqCOL,   linewidth=LW, marker="+", markersize=MS, linestyle=damqLS,   label=damqHS+"")
                if len(faultsHComb) > 0:
                    ax.plot(faultsHComb,   valsHComb,   color=combCOL,   linewidth=LW, marker="+", markersize=MS, linestyle=combLS,   label=combHS+"")
                if len(faultsHDamr) > 0:
                    ax.plot(faultsHDamr,   valsHDamr,   color=damrCOL,   linewidth=LW, marker="+", markersize=MS, linestyle=damrLS,   label=damrHS+"")
                if len(faultsHDama) > 0:
                    ax.plot(faultsHDama,   valsHDama,   color=damaCOL,   linewidth=LW, marker="+", markersize=MS, linestyle=damaLS,   label=damaHS+"")
                if len(faultsHDamp) > 0:
                    ax.plot(faultsHDamp,   valsHDamp,   color=dampCOL,   linewidth=LW, marker="+", markersize=MS, linestyle=dampLS,   label=dampHS+"")
                if len(faultsHFree) > 0:
                    ax.plot(faultsHFree,   valsHFree,   color=freeCOL,   linewidth=LW, marker="+", markersize=MS, linestyle=freeLS,   label=freeHS+"")
                if len(faultsHRoll) > 0:
                    ax.plot(faultsHRoll,   valsHRoll,   color=rollCOL,   linewidth=LW, marker="+", markersize=MS, linestyle=rollLS,   label=rollHS+"")
                if len(faultsHOnep) > 0:
                    ax.plot(faultsHOnep,   valsHOnep,   color=onepCOL,   linewidth=LW, marker="+", markersize=MS, linestyle=onepLS,   label=onepHS+"")
                if len(faultsHOnepB) > 0:
                    ax.plot(faultsHOnepB,  valsHOnepB,  color=onepbCOL,  linewidth=LW, marker="+", markersize=MS, linestyle=onepbLS,  label=onepbHS+"")
                if len(faultsHOnepC) > 0:
                    ax.plot(faultsHOnepC,  valsHOnepC,  color=onepcCOL,  linewidth=LW, marker="+", markersize=MS, linestyle=onepcLS,  label=onepcHS+"")
                if len(faultsHOnepD) > 0:
                    ax.plot(faultsHOnepD,  valsHOnepD,  color=onepdCOL,  linewidth=LW, marker="+", markersize=MS, linestyle=onepdLS,  label=onepdHS+"")
            if plotChained:
                if len(faultsHChBase) > 0:
                    ax.plot(faultsHChBase, valsHChBase, color=baseChCOL, linewidth=LW, marker="+", markersize=MS, linestyle=baseChLS, label=baseChHS+"")
                if len(faultsHChComb) > 0:
                    ax.plot(faultsHChComb, valsHChComb, color=combChCOL, linewidth=LW, marker="+", markersize=MS, linestyle=combChLS, label=combChHS+"")
            if debugPlot:
                if plotBasic:
                    for x,y,z in zip(faultsHBase, valsHBase, numsHBase):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsHCheap, valsHCheap, numsHCheap):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsHQuick, valsHQuick, numsHQuick):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsHDamq, valsHDamq, numsHDamq):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsHComb, valsHComb, numsHComb):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsHDamr, valsHDamr, numsHDamr):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsHDama, valsHDama, numsHDama):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsHDamp, valsHDamp, numsHDamp):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsHFree, valsHFree, numsHFree):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsHRoll, valsHRoll, numsHRoll):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsHOnep, valsHOnep, numsHOnep):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsHOnepB, valsHOnepB, numsHOnepB):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsHOnepC, valsHOnepC, numsHOnepC):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsHOnepD, valsHOnepD, numsHOnepD):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                if plotChained:
                    for x,y,z in zip(faultsHChBase, valsHChBase, numsHChBase):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsHChComb, valsHChComb, numsHChComb):
                        ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
        if plotCrypto: # Sign
            if plotBasic:
                if len(faultsCSBase) > 0:
                    axs[0].plot(faultsCSBase,   valsCSBase,   color=baseCOL,   linewidth=LW, marker="1", markersize=MS, linestyle=baseLS,   label=baseHS+" (crypto-sign)")
                if len(faultsCSCheap) > 0:
                    axs[0].plot(faultsCSCheap,  valsCSCheap,  color=cheapCOL,  linewidth=LW, marker="1", markersize=MS, linestyle=cheapLS,  label=cheapHS+" (crypto-sign)")
                if len(faultsCSQuick) > 0:
                    axs[0].plot(faultsCSQuick,  valsCSQuick,  color=quickCOL,  linewidth=LW, marker="1", markersize=MS, linestyle=quickLS,  label=quickHS+" (crypto-sign)")
                if len(faultsCSDamq) > 0:
                    axs[0].plot(faultsCSDamq,   valsCSDamq,   color=damqCOL,   linewidth=LW, marker="1", markersize=MS, linestyle=damqLS,   label=damqHS+" (crypto-sign)")
                if len(faultsCSComb) > 0:
                    axs[0].plot(faultsCSComb,   valsCSComb,   color=combCOL,   linewidth=LW, marker="1", markersize=MS, linestyle=combLS,   label=combHS+" (crypto-sign)")
                if len(faultsCSDamr) > 0:
                    axs[0].plot(faultsCSDamr,   valsCSDamr,   color=damrCOL,   linewidth=LW, marker="1", markersize=MS, linestyle=damrLS,   label=damrHS+" (crypto-sign)")
                if len(faultsCSDama) > 0:
                    axs[0].plot(faultsCSDama,   valsCSDama,   color=damaCOL,   linewidth=LW, marker="1", markersize=MS, linestyle=damaLS,   label=damaHS+" (crypto-sign)")
                if len(faultsCSDamp) > 0:
                    axs[0].plot(faultsCSDamp,   valsCSDamp,   color=dampCOL,   linewidth=LW, marker="1", markersize=MS, linestyle=dampLS,   label=dampHS+" (crypto-sign)")
                if len(faultsCSFree) > 0:
                    axs[0].plot(faultsCSFree,   valsCSFree,   color=freeCOL,   linewidth=LW, marker="1", markersize=MS, linestyle=freeLS,   label=freeHS+" (crypto-sign)")
                if len(faultsCSRoll) > 0:
                    axs[0].plot(faultsCSRoll,   valsCSRoll,   color=rollCOL,   linewidth=LW, marker="1", markersize=MS, linestyle=rollLS,   label=rollHS+" (crypto-sign)")
                if len(faultsCSOnep) > 0:
                    axs[0].plot(faultsCSOnep,   valsCSOnep,   color=onepCOL,   linewidth=LW, marker="1", markersize=MS, linestyle=onepLS,   label=onepHS+" (crypto-sign)")
                if len(faultsCSOnepB) > 0:
                    axs[0].plot(faultsCSOnepB,  valsCSOnepB,  color=onepbCOL,  linewidth=LW, marker="1", markersize=MS, linestyle=onepbLS,  label=onepbHS+" (crypto-sign)")
                if len(faultsCSOnepC) > 0:
                    axs[0].plot(faultsCSOnepC,  valsCSOnepC,  color=onepcCOL,  linewidth=LW, marker="1", markersize=MS, linestyle=onepcLS,  label=onepcHS+" (crypto-sign)")
                if len(faultsCSOnepD) > 0:
                    axs[0].plot(faultsCSOnepD,  valsCSOnepD,  color=onepdCOL,  linewidth=LW, marker="1", markersize=MS, linestyle=onepdLS,  label=onepdHS+" (crypto-sign)")
            if plotChained:
                if len(faultsCSChBase) > 0:
                    axs[0].plot(faultsCSChBase, valsCSChBase, color=baseChCOL, linewidth=LW, marker="1", markersize=MS, linestyle=baseChLS, label=baseChHS+" (crypto-sign)")
                if len(faultsCSChComb) > 0:
                    axs[0].plot(faultsCSChComb, valsCSChComb, color=combChCOL, linewidth=LW, marker="1", markersize=MS, linestyle=combChLS, label=combChHS+" (crypto-sign)")
            if debugPlot:
                if plotBasic:
                    for x,y,z in zip(faultsCSBase, valsCSBase, numsCSBase):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCSCheap, valsCSCheap, numsCSCheap):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCSQuick, valsCSQuick, numsCSQuick):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCSDamq, valsCSDamq, numsCSDamq):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCSComb, valsCSComb, numsCSComb):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCSDamr, valsCSDamr, numsCSDamr):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCSDama, valsCSDama, numsCSDama):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCSDamp, valsCSDamp, numsCSDamp):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCSFree, valsCSFree, numsCSFree):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCSRoll, valsCSRoll, numsCSRoll):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCSOnep, valsCSOnep, numsCSOnep):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCSOnepB, valsCSOnepB, numsCSOnepB):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCSOnepC, valsCSOnepC, numsCSOnepC):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCSOnepD, valsCSOnepD, numsCSOnepD):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                if plotChained:
                    for x,y,z in zip(faultsCSChBase, valsCSChBase, numsCSChBase):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCSChComb, valsCSChComb, numsCSChComb):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
        if plotCrypto: # Verif
            if plotBasic:
                if len(faultsCVBase) > 0:
                    axs[0].plot(faultsCVBase,   valsCVBase,   color=baseCOL,   linewidth=LW, marker="2", markersize=MS, linestyle=baseLS,   label=baseHS+" (crypto-verif)")
                if len(faultsCVCheap) > 0:
                    axs[0].plot(faultsCVCheap,  valsCVCheap,  color=cheapCOL,  linewidth=LW, marker="2", markersize=MS, linestyle=cheapLS,  label=cheapHS+" (crypto-verif)")
                if len(faultsCVQuick) > 0:
                    axs[0].plot(faultsCVQuick,  valsCVQuick,  color=quickCOL,  linewidth=LW, marker="2", markersize=MS, linestyle=quickLS,  label=quickHS+" (crypto-verif)")
                if len(faultsCVDamq) > 0:
                    axs[0].plot(faultsCVDamq,   valsCVDamq,   color=damqCOL,   linewidth=LW, marker="2", markersize=MS, linestyle=damqLS,   label=damqHS+" (crypto-verif)")
                if len(faultsCVComb) > 0:
                    axs[0].plot(faultsCVComb,   valsCVComb,   color=combCOL,   linewidth=LW, marker="2", markersize=MS, linestyle=combLS,   label=combHS+" (crypto-verif)")
                if len(faultsCVDamr) > 0:
                    axs[0].plot(faultsCVDamr,   valsCVDamr,   color=damrCOL,   linewidth=LW, marker="2", markersize=MS, linestyle=damrLS,   label=damrHS+" (crypto-verif)")
                if len(faultsCVDama) > 0:
                    axs[0].plot(faultsCVDama,   valsCVDama,   color=damaCOL,   linewidth=LW, marker="2", markersize=MS, linestyle=damaLS,   label=damaHS+" (crypto-verif)")
                if len(faultsCVDamp) > 0:
                    axs[0].plot(faultsCVDamp,   valsCVDamp,   color=dampCOL,   linewidth=LW, marker="2", markersize=MS, linestyle=dampLS,   label=dampHS+" (crypto-verif)")
                if len(faultsCVFree) > 0:
                    axs[0].plot(faultsCVFree,   valsCVFree,   color=freeCOL,   linewidth=LW, marker="2", markersize=MS, linestyle=freeLS,   label=freeHS+" (crypto-verif)")
                if len(faultsCVRoll) > 0:
                    axs[0].plot(faultsCVRoll,   valsCVRoll,   color=rollCOL,   linewidth=LW, marker="2", markersize=MS, linestyle=rollLS,   label=rollHS+" (crypto-verif)")
                if len(faultsCVOnep) > 0:
                    axs[0].plot(faultsCVOnep,   valsCVOnep,   color=onepCOL,   linewidth=LW, marker="2", markersize=MS, linestyle=onepLS,   label=onepHS+" (crypto-verif)")
                if len(faultsCVOnepB) > 0:
                    axs[0].plot(faultsCVOnepB,  valsCVOnepB,  color=onepbCOL,  linewidth=LW, marker="2", markersize=MS, linestyle=onepbLS,  label=onepbHS+" (crypto-verif)")
                if len(faultsCVOnepC) > 0:
                    axs[0].plot(faultsCVOnepC,  valsCVOnepC,  color=onepcCOL,  linewidth=LW, marker="2", markersize=MS, linestyle=onepcLS,  label=onepcHS+" (crypto-verif)")
                if len(faultsCVOnepD) > 0:
                    axs[0].plot(faultsCVOnepD,  valsCVOnepD,  color=onepdCOL,  linewidth=LW, marker="2", markersize=MS, linestyle=onepdLS,  label=onepdHS+" (crypto-verif)")
            if plotChained:
                if len(faultsCVChBase) > 0:
                    axs[0].plot(faultsCVChBase, valsCVChBase, color=baseChCOL, linewidth=LW, marker="2", markersize=MS, linestyle=baseChLS, label=baseChHS+" (crypto-verif)")
                if len(faultsCVChComb) > 0:
                    axs[0].plot(faultsCVChComb, valsCVChComb, color=combChCOL, linewidth=LW, marker="2", markersize=MS, linestyle=combChLS, label=combChHS+" (crypto-verif)")
            if debugPlot:
                if plotBasic:
                    for x,y,z in zip(faultsCVBase, valsCVBase, numsCVBase):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCVCheap, valsCVCheap, numsCVCheap):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCVQuick, valsCVQuick, numsCVQuick):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCVDamq, valsCVDamq, numsCVDamq):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCVComb, valsCVComb, numsCVComb):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCVDamr, valsCVDamr, numsCVDamr):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCVDama, valsCVDama, numsCVDama):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCVDamp, valsCVDamp, numsCVDamp):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCVFree, valsCVFree, numsCVFree):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCVRoll, valsCVRoll, numsCVRoll):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCVOnep, valsCVOnep, numsCVOnep):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCVOnepB, valsCVOnepB, numsCVOnepB):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCVOnepC, valsCVOnepC, numsCVOnepC):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCVOnepD, valsCVOnepD, numsCVOnepD):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                if plotChained:
                    for x,y,z in zip(faultsCVChBase, valsCVChBase, numsCVChBase):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    for x,y,z in zip(faultsCVChComb, valsCVChComb, numsCVChComb):
                        axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')

        ax.set_xticks(xs)

        # legend
        if showLegend2 or (showLegend1 and not plotThroughput):
            ax.legend(prop={'size': 9})

    #fig.subplots_adjust(hspace=0.5)
    fig.savefig(plotFile, bbox_inches='tight', pad_inches=0.05)
    print("view-times are in", timesFile)
    print("points are in", pFile)
    print("plot is in", plotFile)
    if displayPlot:
        try:
            subprocess.call([displayApp, plotFile])
        except:
            print("couldn't display the plot using '" + displayApp + "'. Consider changing the 'displayApp' variable.")
    return (dictTVBase, dictTVCheap, dictTVQuick, dictTVDamq, dictTVComb, dictTVDamr, dictTVDama, dictTVDamp, dictTVFree, dictTVRoll, dictTVOnep, dictTVOnepB, dictTVOnepC, dictTVOnepD, dictTVChBase, dictTVChComb,
            dictLVBase, dictLVCheap, dictLVQuick, dictLVDamq, dictLVComb, dictLVDamr, dictLVDama, dictLVDamp, dictLVFree, dictLVRoll, dictLVOnep, dictLVOnepB, dictLVOnepC, dictLVOnepD, dictLVChBase, dictLVChComb)
# End of createPlot


## Plots the points in a view-times file
def createPlotViewTimes(file):
    prot    = ""
    faults  = 0
    vals    = []
    latency = ""
    rate    = ""
    payload = ""

    fig, axs = plt.subplots(1,1)
    axs.set(xlabel="view")
    axs.set(ylabel="time")

    f = open(file,'r')
    for line in f.readlines():
        l = re.split(r'[ \n]+', line)
        l = [x for x in l if x.strip()]
        if line.startswith("## "):
            if len(l) == 4:
                [_,lat,rat,pld] = l
                [_,latency] = lat.split("=")
                [_,rate]    = rat.split("=")
                [_,payload] = pld.split("=")
            else:
                print("unexpected line:", line)
        elif line.startswith("# "):
            if 0 < len(vals):
                # We have values to plot
                xpoints = range(len(vals))
                ypoints = vals
                lab     = prot + "(" + str(faults) + ")"
                print(lab)
                plt.plot(xpoints, ypoints, marker="o", label=lab)

            if len(l) == 3:
                [_,prot,faults] = l
                vals = []
            else:
                print("unexpected line:", line)
        else:
            p    = l[0]
            f    = l[1]
            rest = l[2:]
            if len(vals) == 0:
                vals = [float(x) for x in rest]
            else:
                vals = [ (x[0]+float(x[1]))/2 for x in zip(vals,rest) ]

    if 0 < len(vals):
        xpoints = range(len(vals))
        ypoints = vals
        lab     = prot + "(" + str(faults) + ")"
        plt.plot(xpoints, ypoints, marker="o", label=lab)

    fig.suptitle("latency="+latency+" rate="+rate+" payload="+payload)

    axs.legend(prop={'size': 9})
    pfile = file + ".svg"
    fig.savefig(pfile, bbox_inches='tight', pad_inches=0.05)
    subprocess.call([displayApp, pfile])


def createPlotJoin(pFile):
    # throughput-view
    dictTVBase   = {}
    dictTVCheap  = {}
    dictTVQuick  = {}
    dictTVDamq   = {}
    dictTVComb   = {}
    dictTVDamr   = {}
    dictTVDama   = {}
    dictTVDamp   = {}
    dictTVFree   = {}
    dictTVRoll   = {}
    dictTVOnep   = {}
    dictTVOnepB  = {}
    dictTVOnepC  = {}
    dictTVOnepD  = {}
    dictTVChBase = {}
    dictTVChComb = {}

    # latency-view
    dictLVBase   = {}
    dictLVCheap  = {}
    dictLVQuick  = {}
    dictLVDamq   = {}
    dictLVComb   = {}
    dictLVDamr   = {}
    dictLVDama   = {}
    dictLVDamp   = {}
    dictLVFree   = {}
    dictLVRoll   = {}
    dictLVOnep   = {}
    dictLVOnepB  = {}
    dictLVOnepC  = {}
    dictLVOnepD  = {}
    dictLVChBase = {}
    dictLVChComb = {}

    # handle
    dictHBase   = {}
    dictHCheap  = {}
    dictHQuick  = {}
    dictHDamq   = {}
    dictHComb   = {}
    dictHDamr   = {}
    dictHDama   = {}
    dictHDamp   = {}
    dictHFree   = {}
    dictHRoll   = {}
    dictHOnep   = {}
    dictHOnepB  = {}
    dictHOnepC  = {}
    dictHOnepD  = {}
    dictHChBase = {}
    dictHChComb = {}

    # timeouts
    dictTOBase   = {}
    dictTOCheap  = {}
    dictTOQuick  = {}
    dictTODamq   = {}
    dictTOComb   = {}
    dictTODamr   = {}
    dictTODama   = {}
    dictTODamp   = {}
    dictTOFree   = {}
    dictTORoll   = {}
    dictTOOnep   = {}
    dictTOOnepB  = {}
    dictTOOnepC  = {}
    dictTOOnepD  = {}
    dictTOChBase = {}
    dictTOChComb = {}

    # onepbs
    dictPBBase   = {}
    dictPBCheap  = {}
    dictPBQuick  = {}
    dictPBDamq   = {}
    dictPBComb   = {}
    dictPBDamr   = {}
    dictPBDama   = {}
    dictPBDamp   = {}
    dictPBFree   = {}
    dictPBRoll   = {}
    dictPBOnep   = {}
    dictPBOnepB  = {}
    dictPBOnepC  = {}
    dictPBOnepD  = {}
    dictPBChBase = {}
    dictPBChComb = {}

    # onepcs
    dictPCBase   = {}
    dictPCCheap  = {}
    dictPCQuick  = {}
    dictPCDamq   = {}
    dictPCComb   = {}
    dictPCDamr   = {}
    dictPCDama   = {}
    dictPCDamp   = {}
    dictPCFree   = {}
    dictPCRoll   = {}
    dictPCOnep   = {}
    dictPCOnepB  = {}
    dictPCOnepC  = {}
    dictPCOnepD  = {}
    dictPCChBase = {}
    dictPCChComb = {}

    # crypto-sign
    dictCSBase   = {}
    dictCSCheap  = {}
    dictCSQuick  = {}
    dictCSDamq   = {}
    dictCSComb   = {}
    dictCSDamr   = {}
    dictCSDama   = {}
    dictCSDamp   = {}
    dictCSFree   = {}
    dictCSRoll   = {}
    dictCSOnep   = {}
    dictCSOnepB  = {}
    dictCSOnepC  = {}
    dictCSOnepD  = {}
    dictCSChBase = {}
    dictCSChComb = {}

    # crypto-verif
    dictCVBase   = {}
    dictCVCheap  = {}
    dictCVQuick  = {}
    dictCVDamq   = {}
    dictCVComb   = {}
    dictCVDamr   = {}
    dictCVDama   = {}
    dictCVDamp   = {}
    dictCVFree   = {}
    dictCVRoll   = {}
    dictCVOnep   = {}
    dictCVOnepB  = {}
    dictCVOnepC  = {}
    dictCVOnepD  = {}
    dictCVChBase = {}
    dictCVChComb = {}

    global dockerCpu, dockerMem, networkLat, payloadSize, repeats, repeatsL2, numViews, rateMbit

    # We accumulate all the points in dictionaries
    print("reading points from:", pFile)
    f = open(pFile,'r')
    for line in f.readlines():
        if line.startswith("##params"):
            args = line.split(" ")
            cpu     = "cpus=0"
            mem     = "mem=0"
            lat     = "lat=0"
            rate    = "rate=0"
            payload = "payload=0"
            rep1    = "repeats1=0"
            rep2    = "repeats2=0"
            views   = "views=0"
            regs    = "regions=one"
            if len(args) == 9:
                [hdr,cpu,mem,lat,payload,rep1,rep2,views,regs] = args
            elif len(args) == 10:
                [hdr,cpu,mem,lat,rate,payload,rep1,rep2,views,regs] = args
            else:
                print("WRONG ARGUMENTS in ##params comment")
            [cpuTag,cpuVal] = cpu.split("=")
            dockerCpu = float(cpuVal)
            [memTag,memVal] = mem.split("=")
            dockerMem = int(memVal)
            [latTag,latVal] = lat.split("=")
            networkLat = float(latVal)
            [rateTag,rateVal] = rate.split("=")
            rateMbit = float(rateVal)
            [payloadTag,payloadVal] = payload.split("=")
            payloadSize = int(payloadVal)
            [rep1Tag,rep1Val] = rep1.split("=")
            repeats = int(rep1Val)
            [rep2Tag,rep2Val] = rep2.split("=")
            repeatsL2 = int(rep2Val)
            [viewsTag,viewsVal] = views.split("=")
            numViews = int(viewsVal)
            [regsTag,regsVal] = regs.split("=")
            setRegion(regsVal)

        if line.startswith("protocol"):
            l = line.split(" ")
            prot   = "protocol=BASIC_BASELINE"
            faults = "faults=1"
            joins  = "joiners=0"
            deads  = "deads=0"
            point  = "throughput-view=0.0"
            if len(l) == 3:
                [prot,faults,point] = l
            elif len(l) == 4:
                [prot,faults,deads,point] = l
            elif len(l) == 5:
                [prot,faults,joins,dead,point] = l
            else:
                print("WRONG ARGUMENTS in point line: " + line)
            [protTag,protVal]     = prot.split("=")
            [faultsTag,faultsVal] = faults.split("=")
            [joinsTag,joinsVal]   = joins.split("=")
            [deadsTag,deadsVal]   = deads.split("=")
            [pointTag,pointVal]   = point.split("=")
            numFaults=int(faultsVal)
            numJoins=int(joinsVal)
            numDeads=int(deadsVal)
            if float(pointVal) < float('inf'):
                # Throughputs-view
                if pointTag == "throughput-view":
                    updateDictionaries(protVal,numFaults,numJoins,numDeads,pointVal,dictTVBase,dictTVCheap,dictTVQuick,dictTVDamq,dictTVComb,dictTVDamr,dictTVDama,dictTVDamp,dictTVFree,dictTVRoll,dictTVOnep,dictTVOnepB,dictTVOnepC,dictTVOnepD,dictTVChBase,dictTVChComb)
                # Latencies-view
                if pointTag == "latency-view":
                    updateDictionaries(protVal,numFaults,numJoins,numDeads,pointVal,dictLVBase,dictLVCheap,dictLVQuick,dictLVDamq,dictLVComb,dictLVDamr,dictLVDama,dictLVDamp,dictLVFree,dictLVRoll,dictLVOnep,dictLVOnepB,dictLVOnepC,dictLVOnepD,dictLVChBase,dictLVChComb)
                # handle
                if (pointTag == "handle" or pointTag == "latency-handle"):
                    updateDictionaries(protVal,numFaults,numJoins,numDeads,pointVal,dictHBase,dictHCheap,dictHQuick,dictHDamq,dictHComb,dictHDamr,dictHDama,dictHDamp,dictHFree,dictHRoll,dictHOnep,dictHOnepB,dictHOnepC,dictHOnepD,dictHChBase,dictHChComb)
                # timeouts
                if pointTag == "timeouts":
                    updateDictionaries(protVal,numFaults,numJoins,numDeads,pointVal,dictTOBase,dictTOCheap,dictTOQuick,dictTODamq,dictTOComb,dictTODamr,dictTODama,dictTODamp,dictTOFree,dictTORoll,dictTOOnep,dictTOOnepB,dictTOOnepC,dictTOOnepD,dictTOChBase,dictTOChComb)
                # onepbs
                if pointTag == "onepbs":
                    updateDictionaries(protVal,numFaults,numJoins,numDeads,pointVal,dictPBBase,dictPBCheap,dictPBQuick,dictPBDamq,dictPBComb,dictPBDamr,dictPBDama,dictPBDamp,dictPBFree,dictPBRoll,dictPBOnep,dictPBOnepB,dictPBOnepC,dictPBOnepD,dictPBChBase,dictPBChComb)
                # onepcs
                if pointTag == "onepcs":
                    updateDictionaries(protVal,numFaults,numJoins,numDeads,pointVal,dictPCBase,dictPCCheap,dictPCQuick,dictPCDamq,dictPCComb,dictPCDamr,dictPCDama,dictPCDamp,dictPCFree,dictPCRoll,dictPCOnep,dictPCOnepB,dictPCOnepC,dictPCOnepD,dictPCChBase,dictPCChComb)
                # crypto-sign
                if pointTag == "crypto-sign":
                    updateDictionaries(protVal,numFaults,numJoins,numDeads,pointVal,dictCSBase,dictCSCheap,dictCSQuick,dictCSDamq,dictCSComb,dictCSDamr,dictCSDama,dictCSDamp,dictCSFree,dictCSRoll,dictCSOnep,dictCSOnepB,dictCSOnepC,dictCSOnepD,dictCSChBase,dictCSChComb)
                # crypto-verif
                if pointTag == "crypto-verif":
                    updateDictionaries(protVal,numFaults,numJoins,numDeads,pointVal,dictCVBase,dictCVCheap,dictCVQuick,dictCVDamq,dictCVComb,dictCVDamr,dictCVDama,dictCVDamp,dictCVFree,dictCVRoll,dictCVOnep,dictCVOnepB,dictCVOnepC,dictCVOnepD,dictCVChBase,dictCVChComb)
    f.close()

    quantileSize  = 20
    quantileSize1 = 20
    quantileSize2 = 20

    # We convert the dictionaries to lists
    # throughput-view
    (joinsTVBase,   valsTVBase,   numsTVBase)   = dict2lists(dictTVBase,quantileSize,False,True)
    (joinsTVCheap,  valsTVCheap,  numsTVCheap)  = dict2lists(dictTVCheap,quantileSize,False,True)
    (joinsTVQuick,  valsTVQuick,  numsTVQuick)  = dict2lists(dictTVQuick,quantileSize,False,True)
    (joinsTVDamq,   valsTVDamq,   numsTVDamq)   = dict2lists(dictTVDamq,quantileSize,False,True)
    (joinsTVComb,   valsTVComb,   numsTVComb)   = dict2lists(dictTVComb,quantileSize,False,True)
    (joinsTVDamr,   valsTVDamr,   numsTVDamr)   = dict2lists(dictTVDamr,quantileSize,False,True)
    (joinsTVDama,   valsTVDama,   numsTVDama)   = dict2lists(dictTVDama,quantileSize,False,True)
    (joinsTVDamp,   valsTVDamp,   numsTVDamp)   = dict2lists(dictTVDamp,quantileSize,False,True)
    (joinsTVFree,   valsTVFree,   numsTVFree)   = dict2lists(dictTVFree,quantileSize,False,True)
    (joinsTVRoll,   valsTVRoll,   numsTVRoll)   = dict2lists(dictTVRoll,quantileSize,False,True)
    (joinsTVOnep,   valsTVOnep,   numsTVOnep)   = dict2lists(dictTVOnep,quantileSize,False,True)
    (joinsTVOnepB,  valsTVOnepB,  numsTVOnepB)  = dict2lists(dictTVOnepB,quantileSize,False,True)
    (joinsTVOnepC,  valsTVOnepC,  numsTVOnepC)  = dict2lists(dictTVOnepC,quantileSize,False,True)
    (joinsTVOnepD,  valsTVOnepD,  numsTVOnepD)  = dict2lists(dictTVOnepD,quantileSize,False,True)
    (joinsTVChBase, valsTVChBase, numsTVChBase) = dict2lists(dictTVChBase,quantileSize,False,True)
    (joinsTVChComb, valsTVChComb, numsTVChComb) = dict2lists(dictTVChComb,quantileSize,False,True)

    # latency-view
    (joinsLVBase,   valsLVBase,   numsLVBase)   = dict2lists(dictLVBase,quantileSize,False,True)
    (joinsLVCheap,  valsLVCheap,  numsLVCheap)  = dict2lists(dictLVCheap,quantileSize,False,True)
    (joinsLVQuick,  valsLVQuick,  numsLVQuick)  = dict2lists(dictLVQuick,quantileSize,False,True)
    (joinsLVDamq,   valsLVDamq,   numsLVDamq)   = dict2lists(dictLVDamq,quantileSize,False,True)
    (joinsLVComb,   valsLVComb,   numsLVComb)   = dict2lists(dictLVComb,quantileSize,False,True)
    (joinsLVDamr,   valsLVDamr,   numsLVDamr)   = dict2lists(dictLVDamr,quantileSize,False,True)
    (joinsLVDama,   valsLVDama,   numsLVDama)   = dict2lists(dictLVDama,quantileSize,False,True)
    (joinsLVDamp,   valsLVDamp,   numsLVDamp)   = dict2lists(dictLVDamp,quantileSize,False,True)
    (joinsLVFree,   valsLVFree,   numsLVFree)   = dict2lists(dictLVFree,quantileSize,False,True)
    (joinsLVRoll,   valsLVRoll,   numsLVRoll)   = dict2lists(dictLVRoll,quantileSize,False,True)
    (joinsLVOnep,   valsLVOnep,   numsLVOnep)   = dict2lists(dictLVOnep,quantileSize,False,True)
    (joinsLVOnepB,  valsLVOnepB,  numsLVOnepB)  = dict2lists(dictLVOnepB,quantileSize,False,True)
    (joinsLVOnepC,  valsLVOnepC,  numsLVOnepC)  = dict2lists(dictLVOnepC,quantileSize,False,True)
    (joinsLVOnepD,  valsLVOnepD,  numsLVOnepD)  = dict2lists(dictLVOnepD,quantileSize,False,True)
    (joinsLVChBase, valsLVChBase, numsLVChBase) = dict2lists(dictLVChBase,quantileSize,False,True)
    (joinsLVChComb, valsLVChComb, numsLVChComb) = dict2lists(dictLVChComb,quantileSize,False,True)

    # handle
    (joinsHBase,   valsHBase,   numsHBase)   = dict2lists(dictHBase,quantileSize1,False,True)
    (joinsHCheap,  valsHCheap,  numsHCheap)  = dict2lists(dictHCheap,quantileSize1,False,True)
    (joinsHQuick,  valsHQuick,  numsHQuick)  = dict2lists(dictHQuick,quantileSize1,False,True)
    (joinsHDamq,   valsHDamq,   numsHDamq)   = dict2lists(dictHDamq,quantileSize1,False,True)
    (joinsHComb,   valsHComb,   numsHComb)   = dict2lists(dictHComb,quantileSize1,False,True)
    (joinsHDamr,   valsHDamr,   numsHDamr)   = dict2lists(dictHDamr,quantileSize1,False,True)
    (joinsHDama,   valsHDama,   numsHDama)   = dict2lists(dictHDama,quantileSize1,False,True)
    (joinsHDamp,   valsHDamp,   numsHDamp)   = dict2lists(dictHDamp,quantileSize1,False,True)
    (joinsHFree,   valsHFree,   numsHFree)   = dict2lists(dictHFree,quantileSize1,False,True)
    (joinsHRoll,   valsHRoll,   numsHRoll)   = dict2lists(dictHRoll,quantileSize1,False,True)
    (joinsHOnep,   valsHOnep,   numsHOnep)   = dict2lists(dictHOnep,quantileSize1,False,True)
    (joinsHOnepB,  valsHOnepB,  numsHOnepB)  = dict2lists(dictHOnepB,quantileSize1,False,True)
    (joinsHOnepC,  valsHOnepC,  numsHOnepC)  = dict2lists(dictHOnepC,quantileSize1,False,True)
    (joinsHOnepD,  valsHOnepD,  numsHOnepD)  = dict2lists(dictHOnepD,quantileSize1,False,True)
    (joinsHChBase, valsHChBase, numsHChBase) = dict2lists(dictHChBase,quantileSize1,False,True)
    (joinsHChComb, valsHChComb, numsHChComb) = dict2lists(dictHChComb,quantileSize1,False,True)

    # timeouts
    (joinsTOBase,   valsTOBase,   numsTOBase)   = dict2lists(dictTOBase,0,False,True)
    (joinsTOCheap,  valsTOCheap,  numsTOCheap)  = dict2lists(dictTOCheap,0,False,True)
    (joinsTOQuick,  valsTOQuick,  numsTOQuick)  = dict2lists(dictTOQuick,0,False,True)
    (joinsTODamq,   valsTODamq,   numsTODamq)   = dict2lists(dictTODamq,0,False,True)
    (joinsTOComb,   valsTOComb,   numsTOComb)   = dict2lists(dictTOComb,0,False,True)
    (joinsTODamr,   valsTODamr,   numsTODamr)   = dict2lists(dictTODamr,0,False,True)
    (joinsTODama,   valsTODama,   numsTODama)   = dict2lists(dictTODama,0,False,True)
    (joinsTODamp,   valsTODamp,   numsTODamp)   = dict2lists(dictTODamp,0,False,True)
    (joinsTOFree,   valsTOFree,   numsTOFree)   = dict2lists(dictTOFree,0,False,True)
    (joinsTORoll,   valsTORoll,   numsTORoll)   = dict2lists(dictTORoll,0,False,True)
    (joinsTOOnep,   valsTOOnep,   numsTOOnep)   = dict2lists(dictTOOnep,0,False,True)
    (joinsTOOnepB,  valsTOOnepB,  numsTOOnepB)  = dict2lists(dictTOOnepB,0,False,True)
    (joinsTOOnepC,  valsTOOnepC,  numsTOOnepC)  = dict2lists(dictTOOnepC,0,False,True)
    (joinsTOOnepD,  valsTOOnepD,  numsTOOnepD)  = dict2lists(dictTOOnepD,0,False,True)
    (joinsTOChBase, valsTOChBase, numsTOChBase) = dict2lists(dictTOChBase,0,False,True)
    (joinsTOChComb, valsTOChComb, numsTOChComb) = dict2lists(dictTOChComb,0,False,True)

    # onepbs
    (joinsPBBase,   valsPBBase,   numsPBBase)   = dict2lists(dictPBBase,0,False,True)
    (joinsPBCheap,  valsPBCheap,  numsPBCheap)  = dict2lists(dictPBCheap,0,False,True)
    (joinsPBQuick,  valsPBQuick,  numsPBQuick)  = dict2lists(dictPBQuick,0,False,True)
    (joinsPBDamq,   valsPBDamq,   numsPBDamq)   = dict2lists(dictPBDamq,0,False,True)
    (joinsPBComb,   valsPBComb,   numsPBComb)   = dict2lists(dictPBComb,0,False,True)
    (joinsPBDamr,   valsPBDamr,   numsPBDamr)   = dict2lists(dictPBDamr,0,False,True)
    (joinsPBDama,   valsPBDama,   numsPBDama)   = dict2lists(dictPBDama,0,False,True)
    (joinsPBDamp,   valsPBDamp,   numsPBDamp)   = dict2lists(dictPBDamp,0,False,True)
    (joinsPBFree,   valsPBFree,   numsPBFree)   = dict2lists(dictPBFree,0,False,True)
    (joinsPBRoll,   valsPBRoll,   numsPBRoll)   = dict2lists(dictPBRoll,0,False,True)
    (joinsPBOnep,   valsPBOnep,   numsPBOnep)   = dict2lists(dictPBOnep,0,False,True)
    (joinsPBOnepB,  valsPBOnepB,  numsPBOnepB)  = dict2lists(dictPBOnepB,0,False,True)
    (joinsPBOnepC,  valsPBOnepC,  numsPBOnepC)  = dict2lists(dictPBOnepC,0,False,True)
    (joinsPBOnepD,  valsPBOnepD,  numsPBOnepD)  = dict2lists(dictPBOnepD,0,False,True)
    (joinsPBChBase, valsPBChBase, numsPBChBase) = dict2lists(dictPBChBase,0,False,True)
    (joinsPBChComb, valsPBChComb, numsPBChComb) = dict2lists(dictPBChComb,0,False,True)

    # onepcs
    (joinsPCBase,   valsPCBase,   numsPCBase)   = dict2lists(dictPCBase,0,False,True)
    (joinsPCCheap,  valsPCCheap,  numsPCCheap)  = dict2lists(dictPCCheap,0,False,True)
    (joinsPCQuick,  valsPCQuick,  numsPCQuick)  = dict2lists(dictPCQuick,0,False,True)
    (joinsPCDamq,   valsPCDamq,   numsPCDamq)   = dict2lists(dictPCDamq,0,False,True)
    (joinsPCComb,   valsPCComb,   numsPCComb)   = dict2lists(dictPCComb,0,False,True)
    (joinsPCDamr,   valsPCDamr,   numsPCDamr)   = dict2lists(dictPCDamr,0,False,True)
    (joinsPCDama,   valsPCDama,   numsPCDama)   = dict2lists(dictPCDama,0,False,True)
    (joinsPCDamp,   valsPCDamp,   numsPCDamp)   = dict2lists(dictPCDamp,0,False,True)
    (joinsPCFree,   valsPCFree,   numsPCFree)   = dict2lists(dictPCFree,0,False,True)
    (joinsPCRoll,   valsPCRoll,   numsPCRoll)   = dict2lists(dictPCRoll,0,False,True)
    (joinsPCOnep,   valsPCOnep,   numsPCOnep)   = dict2lists(dictPCOnep,0,False,True)
    (joinsPCOnepB,  valsPCOnepB,  numsPCOnepB)  = dict2lists(dictPCOnepB,0,False,True)
    (joinsPCOnepC,  valsPCOnepC,  numsPCOnepC)  = dict2lists(dictPCOnepC,0,False,True)
    (joinsPCOnepD,  valsPCOnepD,  numsPCOnepD)  = dict2lists(dictPCOnepD,0,False,True)
    (joinsPCChBase, valsPCChBase, numsPCChBase) = dict2lists(dictPCChBase,0,False,True)
    (joinsPCChComb, valsPCChComb, numsPCChComb) = dict2lists(dictPCChComb,0,False,True)

    # crypto-sign
    (joinsCSBase,   valsCSBase,   numsCSBase)   = dict2lists(dictCSBase,quantileSize2,False,True)
    (joinsCSCheap,  valsCSCheap,  numsCSCheap)  = dict2lists(dictCSCheap,quantileSize2,False,True)
    (joinsCSQuick,  valsCSQuick,  numsCSQuick)  = dict2lists(dictCSQuick,quantileSize2,False,True)
    (joinsCSDamq,   valsCSDamq,   numsCSDamq)   = dict2lists(dictCSDamq,quantileSize2,False,True)
    (joinsCSComb,   valsCSComb,   numsCSComb)   = dict2lists(dictCSComb,quantileSize2,False,True)
    (joinsCSDamr,   valsCSDamr,   numsCSDamr)   = dict2lists(dictCSDamr,quantileSize2,False,True)
    (joinsCSDama,   valsCSDama,   numsCSDama)   = dict2lists(dictCSDama,quantileSize2,False,True)
    (joinsCSDamp,   valsCSDamp,   numsCSDamp)   = dict2lists(dictCSDamp,quantileSize2,False,True)
    (joinsCSFree,   valsCSFree,   numsCSFree)   = dict2lists(dictCSFree,quantileSize2,False,True)
    (joinsCSRoll,   valsCSRoll,   numsCSRoll)   = dict2lists(dictCSRoll,quantileSize2,False,True)
    (joinsCSOnep,   valsCSOnep,   numsCSOnep)   = dict2lists(dictCSOnep,quantileSize2,False,True)
    (joinsCSOnepB,  valsCSOnepB,  numsCSOnepB)  = dict2lists(dictCSOnepB,quantileSize2,False,True)
    (joinsCSOnepC,  valsCSOnepC,  numsCSOnepC)  = dict2lists(dictCSOnepC,quantileSize2,False,True)
    (joinsCSOnepD,  valsCSOnepD,  numsCSOnepD)  = dict2lists(dictCSOnepD,quantileSize2,False,True)
    (joinsCSChBase, valsCSChBase, numsCSChBase) = dict2lists(dictCSChBase,quantileSize2,False,True)
    (joinsCSChComb, valsCSChComb, numsCSChComb) = dict2lists(dictCSChComb,quantileSize2,False,True)

    # crypto-verif
    (joinsCVBase,   valsCVBase,   numsCVBase)   = dict2lists(dictCVBase,quantileSize2,False,True)
    (joinsCVCheap,  valsCVCheap,  numsCVCheap)  = dict2lists(dictCVCheap,quantileSize2,False,True)
    (joinsCVQuick,  valsCVQuick,  numsCVQuick)  = dict2lists(dictCVQuick,quantileSize2,False,True)
    (joinsCVDamq,   valsCVDamq,   numsCVDamq)   = dict2lists(dictCVDamq,quantileSize2,False,True)
    (joinsCVComb,   valsCVComb,   numsCVComb)   = dict2lists(dictCVComb,quantileSize2,False,True)
    (joinsCVDamr,   valsCVDamr,   numsCVDamr)   = dict2lists(dictCVDamr,quantileSize2,False,True)
    (joinsCVDama,   valsCVDama,   numsCVDama)   = dict2lists(dictCVDama,quantileSize2,False,True)
    (joinsCVDamp,   valsCVDamp,   numsCVDamp)   = dict2lists(dictCVDamp,quantileSize2,False,True)
    (joinsCVFree,   valsCVFree,   numsCVFree)   = dict2lists(dictCVFree,quantileSize2,False,True)
    (joinsCVRoll,   valsCVRoll,   numsCVRoll)   = dict2lists(dictCVRoll,quantileSize2,False,True)
    (joinsCVOnep,   valsCVOnep,   numsCVOnep)   = dict2lists(dictCVOnep,quantileSize2,False,True)
    (joinsCVOnepB,  valsCVOnepB,  numsCVOnepB)  = dict2lists(dictCVOnepB,quantileSize2,False,True)
    (joinsCVOnepC,  valsCVOnepC,  numsCVOnepC)  = dict2lists(dictCVOnepC,quantileSize2,False,True)
    (joinsCVOnepD,  valsCVOnepD,  numsCVOnepD)  = dict2lists(dictCVOnepD,quantileSize2,False,True)
    (joinsCVChBase, valsCVChBase, numsCVChBase) = dict2lists(dictCVChBase,quantileSize2,False,True)
    (joinsCVChComb, valsCVChComb, numsCVChComb) = dict2lists(dictCVChComb,quantileSize2,False,True)

    print("== faults/throughputs(val+num)/latencies(val+num)/cypto-verif(val+num)/cypto-sign(val+num)")
    if len(joinsTVBase):
        print("base",   (joinsTVBase,   (valsTVBase,   numsTVBase),   (valsLVBase,   numsLVBase),   (valsCVBase,   numsCVBase),   (valsCSBase,   numsCSBase),    (valsTOBase,   numsTOBase)))
    if len(joinsTVCheap):
        print("cheap",  (joinsTVCheap,  (valsTVCheap,  numsTVCheap),  (valsLVCheap,  numsLVCheap),  (valsCVCheap,  numsCVCheap),  (valsCSCheap,  numsCSCheap),   (valsTOCheap,  numsTOCheap)))
    if len(joinsTVQuick):
        print("quick",  (joinsTVQuick,  (valsTVQuick,  numsTVQuick),  (valsLVQuick,  numsLVQuick),  (valsCVQuick,  numsCVQuick),  (valsCSQuick,  numsCSQuick),   (valsTOQuick,  numsTOQuick)))
    if len(joinsTVDamq):
        print("damq",   (joinsTVDamq,   (valsTVDamq,   numsTVDamq),   (valsLVDamq,   numsLVDamq),   (valsCVDamq,   numsCVDamq),   (valsCSDamq,   numsCSDamq),    (valsTODamq,   numsTODamq)))
    if len(joinsTVComb):
        print("comb",   (joinsTVComb,   (valsTVComb,   numsTVComb),   (valsLVComb,   numsLVComb),   (valsCVComb,   numsCVComb),   (valsCSComb,   numsCSComb),    (valsTOComb,   numsTOComb)))
    if len(joinsTVDamr):
        print("damr",   (joinsTVDamr,   (valsTVDamr,   numsTVDamr),   (valsLVDamr,   numsLVDamr),   (valsCVDamr,   numsCVDamr),   (valsCSDamr,   numsCSDamr),    (valsTODamr,   numsTODamr)))
    if len(joinsTVDama):
        print("dama",   (joinsTVDama,   (valsTVDama,   numsTVDama),   (valsLVDama,   numsLVDama),   (valsCVDama,   numsCVDama),   (valsCSDama,   numsCSDama),    (valsTODama,   numsTODama)))
    if len(joinsTVDamp):
        print("damp",   (joinsTVDamp,   (valsTVDamp,   numsTVDamp),   (valsLVDamp,   numsLVDamp),   (valsCVDamp,   numsCVDamp),   (valsCSDamp,   numsCSDamp),    (valsTODamp,   numsTODamp)))
    if len(joinsTVFree):
        print("free",   (joinsTVFree,   (valsTVFree,   numsTVFree),   (valsLVFree,   numsLVFree),   (valsCVFree,   numsCVFree),   (valsCSFree,   numsCSFree),    (valsTOFree,   numsTOFree)))
    if len(joinsTVRoll):
        print("roll",   (joinsTVRoll,   (valsTVRoll,   numsTVRoll),   (valsLVRoll,   numsLVRoll),   (valsCVRoll,   numsCVRoll),   (valsCSRoll,   numsCSRoll),    (valsTORoll,   numsTORoll)))
    if len(joinsTVOnep):
        print("onep",   (joinsTVOnep,   (valsTVOnep,   numsTVOnep),   (valsLVOnep,   numsLVOnep),   (valsCVOnep,   numsCVOnep),   (valsCSOnep,   numsCSOnep),    (valsTOOnep,   numsTOOnep), (valsPBOnep, numsPBOnep), (valsPCOnep, numsPCOnep)))
    if len(joinsTVOnepB):
        print("onepb",  (joinsTVOnepB,  (valsTVOnepB,  numsTVOnepB),  (valsLVOnepB,  numsLVOnepB),  (valsCVOnepB,  numsCVOnepB),  (valsCSOnepB,  numsCSOnepB),   (valsTOOnepB,  numsTOOnepB)))
    if len(joinsTVOnepC):
        print("onepc",  (joinsTVOnepC,  (valsTVOnepC,  numsTVOnepC),  (valsLVOnepC,  numsLVOnepC),  (valsCVOnepC,  numsCVOnepC),  (valsCSOnepC,  numsCSOnepC),   (valsTOOnepC,  numsTOOnepC)))
    if len(joinsTVOnepD):
        print("onepd",  (joinsTVOnepD,  (valsTVOnepD,  numsTVOnepD),  (valsLVOnepD,  numsLVOnepD),  (valsCVOnepD,  numsCVOnepD),  (valsCSOnepD,  numsCSOnepD),   (valsTOOnepD,  numsTOOnepD)))
    if len(joinsTVChBase):
        print("chbase", (joinsTVChBase, (valsTVChBase, numsTVChBase), (valsLVChBase, numsLVChBase), (valsCVChBase, numsCVChBase), (valsCSChBase, numsCSChBase),  (valsTOChBase, numsTOChBase)))
    if len(joinsTVChComb):
        print("chcomb", (joinsTVChComb, (valsTVChComb, numsTVChComb), (valsLVChComb, numsLVChComb), (valsCVChComb, numsCVChComb), (valsCSChComb, numsCSChComb),  (valsTOChComb, numsTOChComb)))

    LW = 1 # linewidth
    MS = 5 # markersize
    XYT = (0,5)

    #plt.figure(figsize=(2, 6))
    #, dpi=80)

    global plotThroughput
    global plotLatency

    if (plotHandle or plotCrypto) and not plotView:
        plotThroughput = False
        plotLatency    = True

    numPlots=2
    if (plotThroughput and not plotLatency) or (not plotThroughput and plotLatency):
        numPlots=1

    ## Plotting
    print("plotting",numPlots,"plot(s)")
    fig, axs = plt.subplots(numPlots,1)
    if numPlots == 1:
        x = axs
        axs = [x]
    #,figsize=(4, 10)
    if showTitle:
        if debugPlot:
            info = "file="+pFile
            info += "; cpus="+str(dockerCpu)
            info += "; mem="+str(dockerMem)
            info += "; lat="+str(networkLat)
            info += "; payload="+str(payloadSize)
            info += "; repeats1="+str(repeats)
            info += "; repeats2="+str(repeatsL2)
            info += "; #views="+str(numViews)
            info += "; #joiners="+str(numJoiners)
            info += "; regions="+regions[0]
            fig.suptitle("Throughputs (top) & Latencies (bottom)\n("+info+")")
#        else:
#            fig.suptitle("Throughputs (top) & Latencies (bottom)")

    adjustFigAspect(fig,aspect=0.9)
    #adjustFigAspect(fig,aspect=0.9)
    if numPlots == 2:
        fig.set_figheight(6)
    else: # == 1
        fig.set_figheight(3)
    #fig.set_figwidth(4)

    if plotThroughput:
        xs = []
        # naming the x/y axis
        #axs[0].set(xlabel="#faults", ylabel="throughput")
        if showYlabel:
            axs[0].set(ylabel="throughput (Kops/s)")
        if logScale:
            axs[0].set_yscale('log')
        if whichExp == "EUexp1":
            axs[0].set_yticks((0.5,1,10,20,70))
            axs[0].set_ylim([0.5,70])
            axs[0].get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        elif whichExp == "ALLexp1":
            axs[0].set_yticks((0.3,1,6))
            axs[0].set_ylim([0.3,6])
            axs[0].get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        # giving a title to my graph
        #axs[0].set_title("throughputs")
        # plotting the points
        if plotView:
            if len(joinsTVBase) > 0:
                axs[0].plot(joinsTVBase,   valsTVBase,   color=baseCOL,   linewidth=LW, marker=baseMRK,   markersize=MS, linestyle=baseLS,   label=baseHS)
                xs = list(set(xs) | set(joinsTVBase))
            if len(joinsTVCheap) > 0:
                axs[0].plot(joinsTVCheap,  valsTVCheap,  color=cheapCOL,  linewidth=LW, marker=cheapMRK,  markersize=MS, linestyle=cheapLS,  label=cheapHS)
                xs = list(set(xs) | set(joinsTVCheap))
            if len(joinsTVQuick) > 0:
                axs[0].plot(joinsTVQuick,  valsTVQuick,  color=quickCOL,  linewidth=LW, marker=quickMRK,  markersize=MS, linestyle=quickLS,  label=quickHS)
                xs = list(set(xs) | set(joinsTVQuick))
            if len(joinsTVDamq) > 0:
                axs[0].plot(joinsTVDamq,   valsTVDamq,   color=damqCOL,   linewidth=LW, marker=damqMRK,   markersize=MS, linestyle=damqLS,   label=damqHS)
                xs = list(set(xs) | set(joinsTVDamq))
            if plotComb and len(joinsTVComb) > 0:
                axs[0].plot(joinsTVComb,   valsTVComb,   color=combCOL,   linewidth=LW, marker=combMRK,   markersize=MS, linestyle=combLS,   label=combHS)
                xs = list(set(xs) | set(joinsTVComb))
            if len(joinsTVDamr) > 0:
                axs[0].plot(joinsTVDamr,   valsTVDamr,   color=damrCOL,   linewidth=LW, marker=damrMRK,   markersize=MS, linestyle=damrLS,   label=damrHS)
                xs = list(set(xs) | set(joinsTVDamr))
            if len(joinsTVDama) > 0:
                axs[0].plot(joinsTVDama,   valsTVDama,   color=damaCOL,   linewidth=LW, marker=damaMRK,   markersize=MS, linestyle=damaLS,   label=damaHS)
                xs = list(set(xs) | set(joinsTVDama))
            if len(joinsTVDamp) > 0:
                axs[0].plot(joinsTVDamp,   valsTVDamp,   color=dampCOL,   linewidth=LW, marker=dampMRK,   markersize=MS, linestyle=dampLS,   label=dampHS)
                xs = list(set(xs) | set(joinsTVDamp))
            if len(joinsTVFree) > 0:
                axs[0].plot(joinsTVFree,   valsTVFree,   color=freeCOL,   linewidth=LW, marker=freeMRK,   markersize=MS, linestyle=freeLS,   label=freeHS)
                xs = list(set(xs) | set(joinsTVFree))
            if len(joinsTVRoll) > 0:
                axs[0].plot(joinsTVRoll,   valsTVRoll,   color=rollCOL,   linewidth=LW, marker=rollMRK,   markersize=MS, linestyle=rollLS,   label=rollHS)
                xs = list(set(xs) | set(joinsTVRoll))
            if len(joinsTVOnep) > 0:
                axs[0].plot(joinsTVOnep,   valsTVOnep,   color=onepCOL,   linewidth=LW, marker=onepMRK,   markersize=MS, linestyle=onepLS,   label=onepHS)
                xs = list(set(xs) | set(joinsTVOnep))
            if len(joinsTVOnepB) > 0:
                axs[0].plot(joinsTVOnepB,  valsTVOnepB,  color=onepbCOL,  linewidth=LW, marker=onepbMRK,  markersize=MS, linestyle=onepbLS,  label=onepbHS)
                xs = list(set(xs) | set(joinsTVOnepB))
            if len(joinsTVOnepC) > 0:
                axs[0].plot(joinsTVOnepC,  valsTVOnepC,  color=onepcCOL,  linewidth=LW, marker=onepcMRK,  markersize=MS, linestyle=onepcLS,  label=onepcHS)
                xs = list(set(xs) | set(joinsTVOnepC))
            if len(joinsTVOnepD) > 0:
                axs[0].plot(joinsTVOnepD,  valsTVOnepD,  color=onepdCOL,  linewidth=LW, marker=onepdMRK,  markersize=MS, linestyle=onepdLS,  label=onepdHS)
                xs = list(set(xs) | set(joinsTVOnepD))
            if debugPlot:
                for x,y,z in zip(joinsTVBase, valsTVBase, numsTVBase):
                    axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsTVCheap, valsTVCheap, numsTVCheap):
                    axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsTVQuick, valsTVQuick, numsTVQuick):
                    axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsTVDamq, valsTVDamq, numsTVDamq):
                    axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsTVComb, valsTVComb, numsTVComb):
                    axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsTVDamr, valsTVDamr, numsTVDamr):
                    axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsTVDama, valsTVDama, numsTVDama):
                    axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsTVDamp, valsTVDamp, numsTVDamp):
                    axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsTVFree, valsTVFree, numsTVFree):
                    axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsTVRoll, valsTVRoll, numsTVRoll):
                    axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsTVOnep, valsTVOnep, numsTVOnep):
                    axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsTVOnepB, valsTVOnepB, numsTVOnepB):
                    axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsTVOnepC, valsTVOnepC, numsTVOnepC):
                    axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsTVOnepD, valsTVOnepD, numsTVOnepD):
                    axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
        axs[0].set_xticks(xs)
        # legend
        if showLegend1:
            axs[0].legend(ncol=2,prop={'size': 9})

    if plotLatency:
        xs = []
        ax=axs[0]
        if plotThroughput:
            ax=axs[1]
        # naming the x/y axis
        if showYlabel:
            ax.set(xlabel="#rejoiners", ylabel="latency (ms)")
        else:
            ax.set(xlabel="#rejoiners")
        if logScale:
            ax.set_yscale('log')
        if whichExp == "EUexp1":
            ax.set_yticks((5,100,600))
            ax.set_ylim([5,600])
            ax.get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        elif whichExp == "ALLexp1":
            ax.set_yticks((60,100,1000))
            ax.set_ylim([60,1000])
            ax.get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        # giving a title to my graph
        #ax.set_title("latencies")
        # plotting the points
        if plotView:
            if len(joinsLVBase) > 0: #and not runBase:
                ax.plot(joinsLVBase,   valsLVBase,   color=baseCOL,   linewidth=LW, marker=baseMRK,   markersize=MS, linestyle=baseLS,   label=baseHS)
                xs = list(set(xs) | set(joinsLVBase))
            if len(joinsLVCheap) > 0: #and not runCheap:
                ax.plot(joinsLVCheap,  valsLVCheap,  color=cheapCOL,  linewidth=LW, marker=cheapMRK,  markersize=MS, linestyle=cheapLS,  label=cheapHS)
                xs = list(set(xs) | set(joinsLVCheap))
            if len(joinsLVQuick) > 0: #and not runQuick:
                ax.plot(joinsLVQuick,  valsLVQuick,  color=quickCOL,  linewidth=LW, marker=quickMRK,  markersize=MS, linestyle=quickLS,  label=quickHS)
                xs = list(set(xs) | set(joinsLVQuick))
            if len(joinsLVDamq) > 0: #and not runDamq:
                ax.plot(joinsLVDamq,   valsLVDamq,   color=damqCOL,   linewidth=LW, marker=damqMRK,   markersize=MS, linestyle=damqLS,   label=damqHS)
                xs = list(set(xs) | set(joinsLVDamq))
            if plotComb and len(joinsLVComb) > 0: #and not runComb:
                ax.plot(joinsLVComb,   valsLVComb,   color=combCOL,   linewidth=LW, marker=combMRK,   markersize=MS, linestyle=combLS,   label=combHS)
                xs = list(set(xs) | set(joinsLVComb))
            if len(joinsLVDamr) > 0: #and not runDamr:
                ax.plot(joinsLVDamr,   valsLVDamr,   color=damrCOL,   linewidth=LW, marker=damrMRK,   markersize=MS, linestyle=damrLS,   label=damrHS)
                xs = list(set(xs) | set(joinsLVDamr))
            if len(joinsLVDama) > 0: #and not runDamr:
                ax.plot(joinsLVDama,   valsLVDama,   color=damaCOL,   linewidth=LW, marker=damaMRK,   markersize=MS, linestyle=damaLS,   label=damaHS)
                xs = list(set(xs) | set(joinsLVDama))
            if len(joinsLVDamp) > 0: #and not runDamp:
                ax.plot(joinsLVDamp,   valsLVDamp,   color=dampCOL,   linewidth=LW, marker=dampMRK,   markersize=MS, linestyle=dampLS,   label=dampHS)
                xs = list(set(xs) | set(joinsLVDamp))
            if len(joinsLVFree) > 0: #and not runFree:
                ax.plot(joinsLVFree,   valsLVFree,   color=freeCOL,   linewidth=LW, marker=freeMRK,   markersize=MS, linestyle=freeLS,   label=freeHS)
                xs = list(set(xs) | set(joinsLVFree))
            if len(joinsLVRoll) > 0: #and not runRoll:
                ax.plot(joinsLVRoll,   valsLVRoll,   color=rollCOL,   linewidth=LW, marker=rollMRK,   markersize=MS, linestyle=rollLS,   label=rollHS)
                xs = list(set(xs) | set(joinsLVRoll))
            if len(joinsLVOnep) > 0: #and not runOnep:
                ax.plot(joinsLVOnep,   valsLVOnep,   color=onepCOL,   linewidth=LW, marker=onepMRK,   markersize=MS, linestyle=onepLS,   label=onepHS)
                xs = list(set(xs) | set(joinsLVOnep))
            if len(joinsLVOnepB) > 0: #and not runOnepB:
                ax.plot(joinsLVOnepB,  valsLVOnepB,  color=onepbCOL,  linewidth=LW, marker=onepbMRK,  markersize=MS, linestyle=onepbLS,  label=onepbHS)
                xs = list(set(xs) | set(joinsLVOnepB))
            if len(joinsLVOnepC) > 0: #and not runOnepC:
                ax.plot(joinsLVOnepC,  valsLVOnepC,  color=onepcCOL,  linewidth=LW, marker=onepcMRK,  markersize=MS, linestyle=onepcLS,  label=onepcHS)
                xs = list(set(xs) | set(joinsLVOnepC))
            if len(joinsLVOnepD) > 0: #and not runOnepD:
                ax.plot(joinsLVOnepD,  valsLVOnepD,  color=onepdCOL,  linewidth=LW, marker=onepdMRK,  markersize=MS, linestyle=onepdLS,  label=onepdHS)
                xs = list(set(xs) | set(joinsLVOnepD))
            if debugPlot:
                for x,y,z in zip(joinsLVBase, valsLVBase, numsLVBase):
                    ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsLVCheap, valsLVCheap, numsLVCheap):
                    ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsLVQuick, valsLVQuick, numsLVQuick):
                    ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsLVDamq, valsLVDamq, numsLVDamq):
                    ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsLVComb, valsLVComb, numsLVComb):
                    ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsLVDamr, valsLVDamr, numsLVDamr):
                    ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsLVDama, valsLVDama, numsLVDama):
                    ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsLVDamp, valsLVDamp, numsLVDamp):
                    ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsLVFree, valsLVFree, numsLVFree):
                    ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsLVRoll, valsLVRoll, numsLVRoll):
                    ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsLVOnep, valsLVOnep, numsLVOnep):
                    ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsLVOnepB, valsLVOnepB, numsLVOnepB):
                    ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsLVOnepC, valsLVOnepC, numsLVOnepC):
                    ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                for x,y,z in zip(joinsLVOnepD, valsLVOnepD, numsLVOnepD):
                    ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
        ax.set_xticks(xs)
        # legend
        if showLegend2 or (showLegend1 and not plotThroughput):
            ax.legend(prop={'size': 9})

    #fig.subplots_adjust(hspace=0.5)
    fig.savefig(plotFile, bbox_inches='tight', pad_inches=0.05)
    print("view-times are in", timesFile)
    print("points are in", pFile)
    print("plot is in", plotFile)
    if displayPlot:
        try:
            subprocess.call([displayApp, plotFile])
        except:
            print("couldn't display the plot using '" + displayApp + "'. Consider changing the 'displayApp' variable.")
    return (dictTVBase, dictTVCheap, dictTVQuick, dictTVDamq, dictTVComb, dictTVDamr, dictTVDama, dictTVDamp, dictTVFree, dictTVRoll, dictTVOnep, dictTVOnepB, dictTVOnepC, dictTVOnepD, dictTVChBase, dictTVChComb,
            dictLVBase, dictLVCheap, dictLVQuick, dictLVDamq, dictLVComb, dictLVDamr, dictLVDama, dictLVDamp, dictLVFree, dictLVRoll, dictLVOnep, dictLVOnepB, dictLVOnepC, dictLVOnepD, dictLVChBase, dictLVChComb)
# End of createPlotJoin


## Alternative versions that generates event plots instead of averages
def createPlotJoin2(pFile):
    dictTV = {} # throughput-view
    dictLV = {} # latency-view
    dictH  = {} # handle
    dictTO = {} # timeouts
    dictPB = {} # onepbs
    dictPC = {} # onepcs
    dictCS = {} # crypto-sign
    dictCV = {} # crypto-verif

    global dockerCpu, dockerMem, networkLat, payloadSize, repeats, repeatsL2, numViews, rateMbit

    # We accumulate all the points in dictionaries
    print("reading points from:", pFile)
    f = open(pFile,'r')
    for line in f.readlines():
        if line.startswith("##params"):
            args = line.split(" ")
            cpu     = "cpus=0"
            mem     = "mem=0"
            lat     = "lat=0"
            rate    = "rate=0"
            payload = "payload=0"
            rep1    = "repeats1=0"
            rep2    = "repeats2=0"
            views   = "views=0"
            regs    = "regions=one"
            if len(args) == 9:
                [hdr,cpu,mem,lat,payload,rep1,rep2,views,regs] = args
            elif len(args) == 10:
                [hdr,cpu,mem,lat,rate,payload,rep1,rep2,views,regs] = args
            else:
                print("WRONG ARGUMENTS in ##params comment")
            [cpuTag,cpuVal] = cpu.split("=")
            dockerCpu = float(cpuVal)
            [memTag,memVal] = mem.split("=")
            dockerMem = int(memVal)
            [latTag,latVal] = lat.split("=")
            networkLat = float(latVal)
            [rateTag,rateVal] = rate.split("=")
            rateMbit = float(rateVal)
            [payloadTag,payloadVal] = payload.split("=")
            payloadSize = int(payloadVal)
            [rep1Tag,rep1Val] = rep1.split("=")
            repeats = int(rep1Val)
            [rep2Tag,rep2Val] = rep2.split("=")
            repeatsL2 = int(rep2Val)
            [viewsTag,viewsVal] = views.split("=")
            numViews = int(viewsVal)
            [regsTag,regsVal] = regs.split("=")
            setRegion(regsVal)

        if line.startswith("protocol"):
            l = line.split(" ")
            prot   = "protocol=BASIC_BASELINE"
            faults = "faults=1"
            joins  = "joiners=0"
            deads  = "deads=0"
            point  = "throughput-view=0.0"
            if len(l) == 3:
                [prot,faults,point] = l
            elif len(l) == 4:
                [prot,faults,deads,point] = l
            elif len(l) == 5:
                [prot,faults,joins,dead,point] = l
            else:
                print("WRONG ARGUMENTS in point line: " + line)
            [protTag,protVal]     = prot.split("=")
            [faultsTag,faultsVal] = faults.split("=")
            [joinsTag,joinsVal]   = joins.split("=")
            [deadsTag,deadsVal]   = deads.split("=")
            [pointTag,pointVal]   = point.split("=")
            numFaults=int(faultsVal)
            numJoins=int(joinsVal)
            numDeads=int(deadsVal)
            if float(pointVal) < float('inf'):
                # Throughputs-view
                if pointTag == "throughput-view":
                    updateDictionary(numJoins,pointVal,dictTV)
                # Latencies-view
                if pointTag == "latency-view":
                    updateDictionary(numJoins,pointVal,dictLV)
                # handle
                if (pointTag == "handle" or pointTag == "latency-handle"):
                    updateDictionary(numJoins,pointVal,dictH)
                # timeouts
                if pointTag == "timeouts":
                    updateDictionary(numJoins,pointVal,dictTO)
                # onepbs
                if pointTag == "onepbs":
                    updateDictionary(numJoins,pointVal,dictPB)
                # onepcs
                if pointTag == "onepcs":
                    updateDictionary(numJoins,pointVal,dictPC)
                # crypto-sign
                if pointTag == "crypto-sign":
                    updateDictionary(numJoins,pointVal,dictCS)
                # crypto-verif
                if pointTag == "crypto-verif":
                    updateDictionary(numJoins,pointVal,dictCV)
    f.close()

    quantileSize  = 20
    quantileSize1 = 20
    quantileSize2 = 20

    # We convert the dictionaries to lists
    (joinsTV,   valsTV,   numsTV)   = dict2lists(dictTV,quantileSize,True,False)  # throughput-view
    (joinsLV,   valsLV,   numsLV)   = dict2lists(dictLV,quantileSize,True,False)  # latency-view
    (joinsH,    valsH,    numsH)    = dict2lists(dictH,quantileSize1,False,False) # handle
    (joinsTO,   valsTO,   numsTO)   = dict2lists(dictTO,0,False,False) # timeouts
    (joinsPB,   valsPB,   numsPB)   = dict2lists(dictPB,0,False,False) # onepbs
    (joinsPC,   valsPC,   numsPC)   = dict2lists(dictPC,0,False,False) # onepcs
    (joinsCS,   valsCS,   numsCS)   = dict2lists(dictCS,quantileSize2,False,False) # crypto-sign
    (joinsCV,   valsCV,   numsCV)   = dict2lists(dictCV,quantileSize2,False,False) # crypto-verif

    print("== faults/throughputs(val+num)/latencies(val+num)/cypto-verif(val+num)/cypto-sign(val+num)")
    if len(joinsTV):
        print((joinsTV,   (valsTV,   numsTV),   (valsLV,   numsLV),   (valsCV,   numsCV),   (valsCS,   numsCS),    (valsTO,   numsTO)))

    LW = 1 # linewidth
    MS = 5 # markersize
    XYT = (0,5)

    #plt.figure(figsize=(2, 6))
    #, dpi=80)

    global plotThroughput
    global plotLatency

    if (plotHandle or plotCrypto) and not plotView:
        plotThroughput = False
        plotLatency    = True

    numPlots=2
    if (plotThroughput and not plotLatency) or (not plotThroughput and plotLatency):
        numPlots=1

    ## Plotting
    print("plotting",numPlots,"plot(s)")
    fig, axs = plt.subplots(numPlots,1)
    if numPlots == 1:
        x = axs
        axs = [x]
    #,figsize=(4, 10)
    if showTitle:
        if debugPlot:
            info = "file="+pFile
            info += "; cpus="+str(dockerCpu)
            info += "; mem="+str(dockerMem)
            info += "; lat="+str(networkLat)
            info += "; payload="+str(payloadSize)
            info += "; repeats1="+str(repeats)
            info += "; repeats2="+str(repeatsL2)
            info += "; #views="+str(numViews)
            info += "; #joiners="+str(numJoiners)
            info += "; regions="+regions[0]
            fig.suptitle("Throughputs (top) & Latencies (bottom)\n("+info+")")
#        else:
#            fig.suptitle("Throughputs (top) & Latencies (bottom)")

    adjustFigAspect(fig,aspect=0.9)
    #adjustFigAspect(fig,aspect=0.9)
    if numPlots == 2:
        fig.set_figheight(6)
    else: # == 1
        fig.set_figheight(3)
    #fig.set_figwidth(4)

    if plotThroughput:
        # naming the x/y axis
        #axs[0].set(xlabel="#faults", ylabel="throughput")
        if showYlabel:
            axs[0].set(ylabel="throughput (Kops/s)")
        if logScale:
            axs[0].set_yscale('log')
        if whichExp == "EUexp1":
            axs[0].set_yticks((0.5,1,10,20,70))
            axs[0].set_ylim([0.5,70])
            axs[0].get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        elif whichExp == "ALLexp1":
            axs[0].set_yticks((0.3,1,6))
            axs[0].set_ylim([0.3,6])
            axs[0].get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        # giving a title to my graph
        #axs[0].set_title("throughputs")
        # plotting the points
        if plotView:
            if len(joinsTV) > 0:
                axs[0].eventplot(valsTV, orientation="vertical", lineoffsets=joinsTV, linewidth=0.2)
                #color=rollCOL, linewidth=LW, marker=rollMRK, markersize=MS, linestyle=rollLS, label=rollHS
            if debugPlot:
                for x,y,z in zip(joinsTV, valsTV, numsTV):
                    axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
        # legend
        if showLegend1:
            axs[0].legend(ncol=2,prop={'size': 9})

    if plotLatency:
        ax=axs[0]
        if plotThroughput:
            ax=axs[1]
        # naming the x/y axis
        if showYlabel:
            ax.set(xlabel="#rejoiners", ylabel="latency (ms)")
        else:
            ax.set(xlabel="#rejoiners")
        if logScale:
            ax.set_yscale('log')
        if whichExp == "EUexp1":
            ax.set_yticks((5,100,600))
            ax.set_ylim([5,600])
            ax.get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        elif whichExp == "ALLexp1":
            ax.set_yticks((60,100,1000))
            ax.set_ylim([60,1000])
            ax.get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        # giving a title to my graph
        #ax.set_title("latencies")
        # plotting the points
        if plotView:
            if len(joinsLV) > 0:
                ax.eventplot(valsLV, orientation="vertical", lineoffsets=joinsLV, linewidth=0.2)
                # color=rollCOL, linewidth=LW, marker=rollMRK, markersize=MS, linestyle=rollLS, label=rollHS
            if debugPlot:
                for x,y,z in zip(joinsLV, valsLV, numsLV):
                    ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
        # legend
        if showLegend2 or (showLegend1 and not plotThroughput):
            ax.legend(prop={'size': 9})

    #fig.subplots_adjust(hspace=0.5)
    fig.savefig(plotFile, bbox_inches='tight', pad_inches=0.05)
    print("view-times are in", timesFile)
    print("points are in", pFile)
    print("plot is in", plotFile)
    if displayPlot:
        try:
            subprocess.call([displayApp, plotFile])
        except:
            print("couldn't display the plot using '" + displayApp + "'. Consider changing the 'displayApp' variable.")
    return (dictTV, dictLV)
# End of createPlotJoin2


def createPlotPayloadAux(pFile):
    # throughput-view
    dictTVBase   = {}
    dictTVCheap  = {}
    dictTVQuick  = {}
    dictTVDamq   = {}
    dictTVComb   = {}
    dictTVDamr   = {}
    dictTVDama   = {}
    dictTVDamp   = {}
    dictTVFree   = {}
    dictTVRoll   = {}
    dictTVOnep   = {}
    dictTVOnepB  = {}
    dictTVOnepC  = {}
    dictTVOnepD  = {}
    dictTVChBase = {}
    dictTVChComb = {}

    # latency-view
    dictLVBase   = {}
    dictLVCheap  = {}
    dictLVQuick  = {}
    dictLVDamq   = {}
    dictLVComb   = {}
    dictLVDamr   = {}
    dictLVDama   = {}
    dictLVDamp   = {}
    dictLVFree   = {}
    dictLVRoll   = {}
    dictLVOnep   = {}
    dictLVOnepB  = {}
    dictLVOnepC  = {}
    dictLVOnepD  = {}
    dictLVChBase = {}
    dictLVChComb = {}

    # handle
    dictHBase   = {}
    dictHCheap  = {}
    dictHQuick  = {}
    dictHDamq   = {}
    dictHComb   = {}
    dictHDamr   = {}
    dictHDama   = {}
    dictHDamp   = {}
    dictHFree   = {}
    dictHRoll   = {}
    dictHOnep   = {}
    dictHOnepB  = {}
    dictHOnepC  = {}
    dictHOnepD  = {}
    dictHChBase = {}
    dictHChComb = {}

    # crypto-sign
    dictCSBase   = {}
    dictCSCheap  = {}
    dictCSQuick  = {}
    dictCSDamq   = {}
    dictCSComb   = {}
    dictCSDamr   = {}
    dictCSDama   = {}
    dictCSDamp   = {}
    dictCSFree   = {}
    dictCSRoll   = {}
    dictCSOnep   = {}
    dictCSOnepB  = {}
    dictCSOnepC  = {}
    dictCSOnepD  = {}
    dictCSChBase = {}
    dictCSChComb = {}

    # crypto-verif
    dictCVBase   = {}
    dictCVCheap  = {}
    dictCVQuick  = {}
    dictCVDamq   = {}
    dictCVComb   = {}
    dictCVDamr   = {}
    dictCVDama   = {}
    dictCVDamp   = {}
    dictCVFree   = {}
    dictCVRoll   = {}
    dictCVOnep   = {}
    dictCVOnepB  = {}
    dictCVOnepC  = {}
    dictCVOnepD  = {}
    dictCVChBase = {}
    dictCVChComb = {}

    global dockerCpu, dockerMem, networkLat, rateMbit, payloadSize, repeats, repeatsL2, numViews

    # We accumulate all the points in dictionaries
    print("reading points from:", pFile)
    f = open(pFile,'r')
    for line in f.readlines():
        if line.startswith("##params"):
            args = line.split(" ")
            cpu     = "cpus=0"
            mem     = "mem=0"
            lat     = "lat=0"
            rate    = "rate=0"
            payload = "payload=0"
            rep1    = "repeats1=0"
            rep2    = "repeats2=0"
            views   = "views=0"
            regs    = "regions=one"
            if len(args) == 9:
                [hdr,cpu,mem,lat,payload,rep1,rep2,views,regs] = args
            elif len(args) == 10:
                [hdr,cpu,mem,lat,rate,payload,rep1,rep2,views,regs] = args
            else:
                print("WRONG ARGUMENTS in ##params comment")
            [cpuTag,cpuVal] = cpu.split("=")
            dockerCpu = float(cpuVal)
            [memTag,memVal] = mem.split("=")
            dockerMem = int(memVal)
            [latTag,latVal] = lat.split("=")
            networkLat = float(latVal)
            [rateTag,rateVal] = rate.split("=")
            rateMbit = float(rateVal)
            [payloadTag,payloadVal] = payload.split("=")
            payloadSize = int(payloadVal)
            [rep1Tag,rep1Val] = rep1.split("=")
            repeats = int(rep1Val)
            [rep2Tag,rep2Val] = rep2.split("=")
            repeatsL2 = int(rep2Val)
            [viewsTag,viewsVal] = views.split("=")
            numViews = int(viewsVal)
            [regsTag,regsVal] = regs.split("=")
            setRegion(regsVal)

        if line.startswith("protocol"):
            [prot,faults,point]   = line.split(" ")
            [protTag,protVal]     = prot.split("=")
            [faultsTag,faultsVal] = faults.split("=")
            [pointTag,pointVal]   = point.split("=")
            numFaults=int(faultsVal)
            if float(pointVal) < float('inf'):
                # Throughputs-view
                if pointTag == "throughput-view" and protVal == "BASIC_BASELINE":
                    (val,num) = dictTVBase.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictTVBase.update({payloadSize:(val,num+1)})
                if pointTag == "throughput-view" and protVal == "BASIC_CHEAP":
                    (val,num) = dictTVCheap.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictTVCheap.update({payloadSize:(val,num+1)})
                if pointTag == "throughput-view" and protVal == "BASIC_QUICK":
                    (val,num) = dictTVQuick.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictTVQuick.update({payloadSize:(val,num+1)})
                if pointTag == "throughput-view" and protVal == "BASIC_QUICK_DEBUG":
                    (val,num) = dictTVQuick.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictTVQuick.update({payloadSize:(val,num+1)})
                if pointTag == "throughput-view" and protVal == "BASIC_CHEAP_AND_QUICK":
                    (val,num) = dictTVComb.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictTVComb.update({payloadSize:(val,num+1)})
                if pointTag == "throughput-view" and protVal == "BASIC_DAMYSUS_ROTE":
                    (val,num) = dictTVDamr.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictTVDamr.update({payloadSize:(val,num+1)})
                if pointTag == "throughput-view" and protVal == "BASIC_DAMYSUS_ACHILLES":
                    (val,num) = dictTVDama.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictTVDama.update({payloadSize:(val,num+1)})
                if pointTag == "throughput-view" and protVal == "BASIC_DAMYSUS_PACEMAKER":
                    (val,num) = dictTVDamp.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictTVDamp.update({payloadSize:(val,num+1)})
                if pointTag == "throughput-view" and protVal == "BASIC_DAMYSUS3_PACEMAKER":
                    (val,num) = dictTVDamq.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictTVDamq.update({payloadSize:(val,num+1)})
                if pointTag == "throughput-view" and protVal == "BASIC_FREE":
                    (val,num) = dictTVFree.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictTVFree.update({payloadSize:(val,num+1)})
                if pointTag == "throughput-view" and protVal == "BASIC_ROLL":
                    (val,num) = dictTVRoll.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictTVRoll.update({payloadSize:(val,num+1)})
                if pointTag == "throughput-view" and protVal == "BASIC_ONEP":
                    (val,num) = dictTVOnep.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictTVOnep.update({payloadSize:(val,num+1)})
                if pointTag == "throughput-view" and protVal == "CHAINED_BASELINE":
                    (val,num) = dictTVChBase.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictTVChBase.update({payloadSize:(val,num+1)})
                if pointTag == "throughput-view" and protVal == "CHAINED_CHEAP_AND_QUICK":
                    (val,num) = dictTVChComb.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictTVChComb.update({payloadSize:(val,num+1)})
                if pointTag == "throughput-view" and protVal == "CHAINED_CHEAP_AND_QUICK_DEBUG":
                    (val,num) = dictTVChComb.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictTVChComb.update({payloadSize:(val,num+1)})
                # Latencies-view
                if pointTag == "latency-view" and protVal == "BASIC_BASELINE":
                    (val,num) = dictLVBase.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictLVBase.update({payloadSize:(val,num+1)})
                if pointTag == "latency-view" and protVal == "BASIC_CHEAP":
                    (val,num) = dictLVCheap.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictLVCheap.update({payloadSize:(val,num+1)})
                if pointTag == "latency-view" and protVal == "BASIC_QUICK":
                    (val,num) = dictLVQuick.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictLVQuick.update({payloadSize:(val,num+1)})
                if pointTag == "latency-view" and protVal == "BASIC_QUICK_DEBUG":
                    (val,num) = dictLVQuick.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictLVQuick.update({payloadSize:(val,num+1)})
                if pointTag == "latency-view" and protVal == "BASIC_CHEAP_AND_QUICK":
                    (val,num) = dictLVComb.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictLVComb.update({payloadSize:(val,num+1)})
                if pointTag == "latency-view" and protVal == "BASIC_DAMYSUS_ROTE":
                    (val,num) = dictLVDamr.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictLVDamr.update({payloadSize:(val,num+1)})
                if pointTag == "latency-view" and protVal == "BASIC_DAMYSUS_ACHILLES":
                    (val,num) = dictLVDama.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictLVDama.update({payloadSize:(val,num+1)})
                if pointTag == "latency-view" and protVal == "BASIC_DAMYSUS_PACEMAKER":
                    (val,num) = dictLVDamp.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictLVDamp.update({payloadSize:(val,num+1)})
                if pointTag == "latency-view" and protVal == "BASIC_DAMYSUS3_PACEMAKER":
                    (val,num) = dictLVDamq.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictLVDamq.update({payloadSize:(val,num+1)})
                if pointTag == "latency-view" and protVal == "BASIC_FREE":
                    (val,num) = dictLVFree.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictLVFree.update({payloadSize:(val,num+1)})
                if pointTag == "latency-view" and protVal == "BASIC_ROLL":
                    (val,num) = dictLVRoll.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictLVRoll.update({payloadSize:(val,num+1)})
                if pointTag == "latency-view" and protVal == "BASIC_ONEP":
                    (val,num) = dictLVOnep.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictLVOnep.update({payloadSize:(val,num+1)})
                if pointTag == "latency-view" and protVal == "CHAINED_BASELINE":
                    (val,num) = dictLVChBase.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictLVChBase.update({payloadSize:(val,num+1)})
                if pointTag == "latency-view" and protVal == "CHAINED_CHEAP_AND_QUICK":
                    (val,num) = dictLVChComb.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictLVChComb.update({payloadSize:(val,num+1)})
                if pointTag == "latency-view" and protVal == "CHAINED_CHEAP_AND_QUICK_DEBUG":
                    (val,num) = dictLVChComb.get(payloadSize,([],0))
                    val.append(float(pointVal))
                    dictLVChComb.update({payloadSize:(val,num+1)})
                # handle
                if (pointTag == "handle" or pointTag == "latency-handle") and protVal == "BASIC_BASELINE":
                    (val,num) = dictHBase.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictHBase.update({payloadSize:(val,num+1)})
                if (pointTag == "handle" or pointTag == "latency-handle") and protVal == "BASIC_CHEAP":
                    (val,num) = dictHCheap.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictHCheap.update({payloadSize:(val,num+1)})
                if (pointTag == "handle" or pointTag == "latency-handle") and protVal == "BASIC_QUICK":
                    (val,num) = dictHQuick.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictHQuick.update({payloadSize:(val,num+1)})
                if (pointTag == "handle" or pointTag == "latency-handle") and protVal == "BASIC_QUICK_DEBUG":
                    (val,num) = dictHQuick.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictHQuick.update({payloadSize:(val,num+1)})
                if (pointTag == "handle" or pointTag == "latency-handle") and protVal == "BASIC_CHEAP_AND_QUICK":
                    (val,num) = dictHComb.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictHComb.update({payloadSize:(val,num+1)})
                if (pointTag == "handle" or pointTag == "latency-handle") and protVal == "BASIC_DAMYSUS_ROTE":
                    (val,num) = dictHDamr.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictHDamr.update({payloadSize:(val,num+1)})
                if (pointTag == "handle" or pointTag == "latency-handle") and protVal == "BASIC_DAMYSUS_ACHILLES":
                    (val,num) = dictHDama.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictHDama.update({payloadSize:(val,num+1)})
                if (pointTag == "handle" or pointTag == "latency-handle") and protVal == "BASIC_DAMYSUS_PACEMAKER":
                    (val,num) = dictHDamp.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictHDamp.update({payloadSize:(val,num+1)})
                if (pointTag == "handle" or pointTag == "latency-handle") and protVal == "BASIC_DAMYSUS3_PACEMAKER":
                    (val,num) = dictHDamq.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictHDamq.update({payloadSize:(val,num+1)})
                if (pointTag == "handle" or pointTag == "latency-handle") and protVal == "BASIC_FREE":
                    (val,num) = dictHFree.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictHFree.update({payloadSize:(val,num+1)})
                if (pointTag == "handle" or pointTag == "latency-handle") and protVal == "BASIC_ROLL":
                    (val,num) = dictHRoll.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictHRoll.update({payloadSize:(val,num+1)})
                if (pointTag == "handle" or pointTag == "latency-handle") and protVal == "BASIC_ONEP":
                    (val,num) = dictHOnep.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictHOnep.update({payloadSize:(val,num+1)})
                if (pointTag == "handle" or pointTag == "latency-handle") and protVal == "CHAINED_BASELINE":
                    (val,num) = dictHChBase.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictHChBase.update({payloadSize:(val,num+1)})
                if (pointTag == "handle" or pointTag == "latency-handle") and protVal == "CHAINED_CHEAP_AND_QUICK":
                    (val,num) = dictHChComb.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictHChComb.update({payloadSize:(val,num+1)})
                if (pointTag == "handle" or pointTag == "latency-handle") and protVal == "CHAINED_CHEAP_AND_QUICK_DEBUG":
                    (val,num) = dictHChComb.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictHChComb.update({payloadSize:(val,num+1)})
                # crypto-sign
                if pointTag == "crypto-sign" and protVal == "BASIC_BASELINE":
                    (val,num) = dictCSBase.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCSBase.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-sign" and protVal == "BASIC_CHEAP":
                    (val,num) = dictCSCheap.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCSCheap.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-sign" and protVal == "BASIC_QUICK":
                    (val,num) = dictCSQuick.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCSQuick.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-sign" and protVal == "BASIC_QUICK_DEBUG":
                    (val,num) = dictCSQuick.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCSQuick.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-sign" and protVal == "BASIC_CHEAP_AND_QUICK":
                    (val,num) = dictCSComb.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCSComb.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-sign" and protVal == "BASIC_DAMYSUS_ROTE":
                    (val,num) = dictCSDamr.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCSDamr.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-sign" and protVal == "BASIC_DAMYSUS_ACHILLES":
                    (val,num) = dictCSDama.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCSDama.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-sign" and protVal == "BASIC_DAMYSUS_PACEMAKER":
                    (val,num) = dictCSDamp.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCSDamp.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-sign" and protVal == "BASIC_DAMYSUS3_PACEMAKER":
                    (val,num) = dictCSDamq.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCSDamq.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-sign" and protVal == "BASIC_FREE":
                    (val,num) = dictCSFree.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCSFree.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-sign" and protVal == "BASIC_ROLL":
                    (val,num) = dictCSRoll.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCSRoll.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-sign" and protVal == "BASIC_ONEP":
                    (val,num) = dictCSOnep.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCSOnep.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-sign" and protVal == "CHAINED_BASELINE":
                    (val,num) = dictCSChBase.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCSChBase.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-sign" and protVal == "CHAINED_CHEAP_AND_QUICK":
                    (val,num) = dictCSChComb.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCSChComb.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-sign" and protVal == "CHAINED_CHEAP_AND_QUICK_DEBUG":
                    (val,num) = dictCSChComb.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCSChComb.update({payloadSize:(val,num+1)})
                # crypto-verif
                if pointTag == "crypto-verif" and protVal == "BASIC_BASELINE":
                    (val,num) = dictCVBase.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCVBase.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-verif" and protVal == "BASIC_CHEAP":
                    (val,num) = dictCVCheap.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCVCheap.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-verif" and protVal == "BASIC_QUICK":
                    (val,num) = dictCVQuick.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCVQuick.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-verif" and protVal == "BASIC_QUICK_DEBUG":
                    (val,num) = dictCVQuick.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCVQuick.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-verif" and protVal == "BASIC_CHEAP_AND_QUICK":
                    (val,num) = dictCVComb.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCVComb.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-verif" and protVal == "BASIC_DAMSUS_ROTE":
                    (val,num) = dictCVDamr.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCVDamr.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-verif" and protVal == "BASIC_DAMSUS_ACHILLES":
                    (val,num) = dictCVDama.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCVDama.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-verif" and protVal == "BASIC_DAMSUS_PACEMAKER":
                    (val,num) = dictCVDamp.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCVDamp.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-verif" and protVal == "BASIC_DAMYSUS3_PACEMAKER":
                    (val,num) = dictCVDamq.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCVDamq.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-verif" and protVal == "BASIC_FREE":
                    (val,num) = dictCVFree.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCVFree.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-verif" and protVal == "BASIC_ROLL":
                    (val,num) = dictCVRoll.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCVRoll.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-verif" and protVal == "BASIC_ONEP":
                    (val,num) = dictCVOnep.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCVOnep.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-verif" and protVal == "CHAINED_BASELINE":
                    (val,num) = dictCVChBase.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCVChBase.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-verif" and protVal == "CHAINED_CHEAP_AND_QUICK":
                    (val,num) = dictCVChComb.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCVChComb.update({payloadSize:(val,num+1)})
                if pointTag == "crypto-verif" and protVal == "CHAINED_CHEAP_AND_QUICK_DEBUG":
                    (val,num) = dictCVChComb.get(payloadSize,([],0))
                    val.append(float(pointVal) / numViews)
                    dictCVChComb.update({payloadSize:(val,num+1)})
    f.close()

    quantileSize = 20
    quantileSize1 = 20
    quantileSize2 = 20

    # We convert the dictionaries to lists
    # throughput-view
    (payloadsTVBase,   valsTVBase,   numsTVBase)   = dict2lists(dictTVBase,quantileSize,False,True)
    (payloadsTVCheap,  valsTVCheap,  numsTVCheap)  = dict2lists(dictTVCheap,quantileSize,False,True)
    (payloadsTVQuick,  valsTVQuick,  numsTVQuick)  = dict2lists(dictTVQuick,quantileSize,False,True)
    (payloadsTVDamq,   valsTVDamq,   numsTVDamq)   = dict2lists(dictTVDamq,quantileSize,False,True)
    (payloadsTVComb,   valsTVComb,   numsTVComb)   = dict2lists(dictTVComb,quantileSize,False,True)
    (payloadsTVDamr,   valsTVDamr,   numsTVDamr)   = dict2lists(dictTVDamr,quantileSize,False,True)
    (payloadsTVDama,   valsTVDama,   numsTVDama)   = dict2lists(dictTVDama,quantileSize,False,True)
    (payloadsTVDamp,   valsTVDamp,   numsTVDamp)   = dict2lists(dictTVDamp,quantileSize,False,True)
    (payloadsTVFree,   valsTVFree,   numsTVFree)   = dict2lists(dictTVFree,quantileSize,False,True)
    (payloadsTVRoll,   valsTVRoll,   numsTVRoll)   = dict2lists(dictTVRoll,quantileSize,False,True)
    (payloadsTVOnep,   valsTVOnep,   numsTVOnep)   = dict2lists(dictTVOnep,quantileSize,False,True)
    (payloadsTVChBase, valsTVChBase, numsTVChBase) = dict2lists(dictTVChBase,quantileSize,False,True)
    (payloadsTVChComb, valsTVChComb, numsTVChComb) = dict2lists(dictTVChComb,quantileSize,False,True)
    # latency-view
    (payloadsLVBase,   valsLVBase,   numsLVBase)   = dict2lists(dictLVBase,quantileSize,False,True)
    (payloadsLVCheap,  valsLVCheap,  numsLVCheap)  = dict2lists(dictLVCheap,quantileSize,False,True)
    (payloadsLVQuick,  valsLVQuick,  numsLVQuick)  = dict2lists(dictLVQuick,quantileSize,False,True)
    (payloadsLVDamq,   valsLVDamq,   numsLVDamq)   = dict2lists(dictLVDamq,quantileSize,False,True)
    (payloadsLVComb,   valsLVComb,   numsLVComb)   = dict2lists(dictLVComb,quantileSize,False,True)
    (payloadsLVDamr,   valsLVDamr,   numsLVDamr)   = dict2lists(dictLVDamr,quantileSize,False,True)
    (payloadsLVDama,   valsLVDama,   numsLVDama)   = dict2lists(dictLVDama,quantileSize,False,True)
    (payloadsLVDamp,   valsLVDamp,   numsLVDamp)   = dict2lists(dictLVDamp,quantileSize,False,True)
    (payloadsLVFree,   valsLVFree,   numsLVFree)   = dict2lists(dictLVFree,quantileSize,False,True)
    (payloadsLVRoll,   valsLVRoll,   numsLVRoll)   = dict2lists(dictLVRoll,quantileSize,False,True)
    (payloadsLVOnep,   valsLVOnep,   numsLVOnep)   = dict2lists(dictLVOnep,quantileSize,False,True)
    (payloadsLVChBase, valsLVChBase, numsLVChBase) = dict2lists(dictLVChBase,quantileSize,False,True)
    (payloadsLVChComb, valsLVChComb, numsLVChComb) = dict2lists(dictLVChComb,quantileSize,False,True)
    # handle
    (payloadsHBase,   valsHBase,   numsHBase)   = dict2lists(dictHBase,quantileSize1,False,True)
    (payloadsHCheap,  valsHCheap,  numsHCheap)  = dict2lists(dictHCheap,quantileSize1,False,True)
    (payloadsHQuick,  valsHQuick,  numsHQuick)  = dict2lists(dictHQuick,quantileSize1,False,True)
    (payloadsHDamq,   valsHDamq,   numsHDamq)   = dict2lists(dictHDamq,quantileSize1,False,True)
    (payloadsHComb,   valsHComb,   numsHComb)   = dict2lists(dictHComb,quantileSize1,False,True)
    (payloadsHDamr,   valsHDamr,   numsHDamr)   = dict2lists(dictHDamr,quantileSize1,False,True)
    (payloadsHDama,   valsHDama,   numsHDama)   = dict2lists(dictHDama,quantileSize1,False,True)
    (payloadsHDamp,   valsHDamp,   numsHDamp)   = dict2lists(dictHDamp,quantileSize1,False,True)
    (payloadsHFree,   valsHFree,   numsHFree)   = dict2lists(dictHFree,quantileSize1,False,True)
    (payloadsHRoll,   valsHRoll,   numsHRoll)   = dict2lists(dictHRoll,quantileSize1,False,True)
    (payloadsHOnep,   valsHOnep,   numsHOnep)   = dict2lists(dictHOnep,quantileSize1,False,True)
    (payloadsHChBase, valsHChBase, numsHChBase) = dict2lists(dictHChBase,quantileSize1,False,True)
    (payloadsHChComb, valsHChComb, numsHChComb) = dict2lists(dictHChComb,quantileSize1,False,True)
    # crypto-sign
    (payloadsCSBase,   valsCSBase,   numsCSBase)   = dict2lists(dictCSBase,quantileSize2,False,True)
    (payloadsCSCheap,  valsCSCheap,  numsCSCheap)  = dict2lists(dictCSCheap,quantileSize2,False,True)
    (payloadsCSQuick,  valsCSQuick,  numsCSQuick)  = dict2lists(dictCSQuick,quantileSize2,False,True)
    (payloadsCSDamq,   valsCSDamq,   numsCSDamq)   = dict2lists(dictCSDamq,quantileSize2,False,True)
    (payloadsCSComb,   valsCSComb,   numsCSComb)   = dict2lists(dictCSComb,quantileSize2,False,True)
    (payloadsCSDamr,   valsCSDamr,   numsCSDamr)   = dict2lists(dictCSDamr,quantileSize2,False,True)
    (payloadsCSDama,   valsCSDama,   numsCSDama)   = dict2lists(dictCSDama,quantileSize2,False,True)
    (payloadsCSDamp,   valsCSDamp,   numsCSDamp)   = dict2lists(dictCSDamp,quantileSize2,False,True)
    (payloadsCSFree,   valsCSFree,   numsCSFree)   = dict2lists(dictCSFree,quantileSize2,False,True)
    (payloadsCSRoll,   valsCSRoll,   numsCSRoll)   = dict2lists(dictCSRoll,quantileSize2,False,True)
    (payloadsCSOnep,   valsCSOnep,   numsCSOnep)   = dict2lists(dictCSOnep,quantileSize2,False,True)
    (payloadsCSChBase, valsCSChBase, numsCSChBase) = dict2lists(dictCSChBase,quantileSize2,False,True)
    (payloadsCSChComb, valsCSChComb, numsCSChComb) = dict2lists(dictCSChComb,quantileSize2,False,True)
    # crypto-verif
    (payloadsCVBase,   valsCVBase,   numsCVBase)   = dict2lists(dictCVBase,quantileSize2,False,True)
    (payloadsCVCheap,  valsCVCheap,  numsCVCheap)  = dict2lists(dictCVCheap,quantileSize2,False,True)
    (payloadsCVQuick,  valsCVQuick,  numsCVQuick)  = dict2lists(dictCVQuick,quantileSize2,False,True)
    (payloadsCVDamq,   valsCVDamq,   numsCVDamq)   = dict2lists(dictCVDamq,quantileSize2,False,True)
    (payloadsCVComb,   valsCVComb,   numsCVComb)   = dict2lists(dictCVComb,quantileSize2,False,True)
    (payloadsCVDamr,   valsCVDamr,   numsCVDamr)   = dict2lists(dictCVDamr,quantileSize2,False,True)
    (payloadsCVDama,   valsCVDama,   numsCVDama)   = dict2lists(dictCVDama,quantileSize2,False,True)
    (payloadsCVDamp,   valsCVDamp,   numsCVDamp)   = dict2lists(dictCVDamp,quantileSize2,False,True)
    (payloadsCVFree,   valsCVFree,   numsCVFree)   = dict2lists(dictCVFree,quantileSize2,False,True)
    (payloadsCVRoll,   valsCVRoll,   numsCVRoll)   = dict2lists(dictCVRoll,quantileSize2,False,True)
    (payloadsCVOnep,   valsCVOnep,   numsCVOnep)   = dict2lists(dictCVOnep,quantileSize2,False,True)
    (payloadsCVChBase, valsCVChBase, numsCVChBase) = dict2lists(dictCVChBase,quantileSize2,False,True)
    (payloadsCVChComb, valsCVChComb, numsCVChComb) = dict2lists(dictCVChComb,quantileSize2,False,True)

    print("payloads/throughputs(val+num)/latencies(val+num)/cypto-verif(val+num)/cypto-sign(val+num) for (baseline/cheap/quick/damq/combined/damysus+rote/free/roll/onep/chained-baseline/chained-combined)")
    print((payloadsTVBase,   (valsTVBase,   numsTVBase),   (valsLVBase,   numsLVBase),   (valsCVBase,   numsCVBase),   (valsCSBase,   numsCSBase)))
    print((payloadsTVCheap,  (valsTVCheap,  numsTVCheap),  (valsLVCheap,  numsLVCheap),  (valsCVCheap,  numsCVCheap),  (valsCSCheap,  numsCSCheap)))
    print((payloadsTVQuick,  (valsTVQuick,  numsTVQuick),  (valsLVQuick,  numsLVQuick),  (valsCVQuick,  numsCVQuick),  (valsCSQuick,  numsCSQuick)))
    print((payloadsTVDamq,   (valsTVDamq,   numsTVDamq),   (valsLVDamq,   numsLVDamq),   (valsCVDamq,   numsCVDamq),   (valsCSDamq,   numsCSDamq)))
    print((payloadsTVComb,   (valsTVComb,   numsTVComb),   (valsLVComb,   numsLVComb),   (valsCVComb,   numsCVComb),   (valsCSComb,   numsCSComb)))
    print((payloadsTVDamr,   (valsTVDamr,   numsTVDamr),   (valsLVDamr,   numsLVDamr),   (valsCVDamr,   numsCVDamr),   (valsCSDamr,   numsCSDamr)))
    print((payloadsTVDama,   (valsTVDama,   numsTVDama),   (valsLVDama,   numsLVDama),   (valsCVDama,   numsCVDama),   (valsCSDama,   numsCSDama)))
    print((payloadsTVDamp,   (valsTVDamp,   numsTVDamp),   (valsLVDamp,   numsLVDamp),   (valsCVDamp,   numsCVDamp),   (valsCSDamp,   numsCSDamp)))
    print((payloadsTVFree,   (valsTVFree,   numsTVFree),   (valsLVFree,   numsLVFree),   (valsCVFree,   numsCVFree),   (valsCSFree,   numsCSFree)))
    print((payloadsTVRoll,   (valsTVRoll,   numsTVRoll),   (valsLVRoll,   numsLVRoll),   (valsCVRoll,   numsCVRoll),   (valsCSRoll,   numsCSRoll)))
    print((payloadsTVOnep,   (valsTVOnep,   numsTVOnep),   (valsLVOnep,   numsLVOnep),   (valsCVOnep,   numsCVOnep),   (valsCSOnep,   numsCSOnep)))
    print((payloadsTVChBase, (valsTVChBase, numsTVChBase), (valsLVChBase, numsLVChBase), (valsCVChBase, numsCVChBase), (valsCSChBase, numsCSChBase)))
    print((payloadsTVChComb, (valsTVChComb, numsTVChComb), (valsLVChComb, numsLVChComb), (valsCVChComb, numsCVChComb), (valsCSChComb, numsCSChComb)))

    print("Throughput gain (basic versions):")
    # non-chained
    getPercentage(False,baseHS,payloadsTVBase,valsTVBase,cheapHS,payloadsTVCheap,valsTVCheap)
    getPercentage(False,baseHS,payloadsTVBase,valsTVBase,quickHS,payloadsTVQuick,valsTVQuick)
    getPercentage(False,baseHS,payloadsTVBase,valsTVBase,damqHS, payloadsTVDamq, valsTVDamq)
    getPercentage(False,baseHS,payloadsTVBase,valsTVBase,combHS, payloadsTVComb, valsTVComb)
    getPercentage(False,baseHS,payloadsTVBase,valsTVBase,damrHS, payloadsTVDamr, valsTVDamr)
    getPercentage(False,baseHS,payloadsTVBase,valsTVBase,damaHS, payloadsTVDama, valsTVDama)
    getPercentage(False,baseHS,payloadsTVBase,valsTVBase,dampHS, payloadsTVDamp, valsTVDamp)
    getPercentage(False,baseHS,payloadsTVBase,valsTVBase,freeHS, payloadsTVFree, valsTVFree)
    getPercentage(False,combHS,payloadsTVComb,valsTVComb,freeHS, payloadsTVFree, valsTVFree)
    getPercentage(False,baseHS,payloadsTVBase,valsTVBase,onepHS, payloadsTVOnep, valsTVOnep)
    getPercentage(False,combHS,payloadsTVComb,valsTVComb,onepHS, payloadsTVOnep, valsTVOnep)
    # chained
    getPercentage(False,baseChHS,payloadsTVChBase,valsTVChBase,combChHS,payloadsTVChComb,valsTVChComb)

    print("Latency gain (basic versions):")
    # non-chained
    getPercentage(True,baseHS,payloadsLVBase,valsLVBase,cheapHS,payloadsLVCheap,valsLVCheap)
    getPercentage(True,baseHS,payloadsLVBase,valsLVBase,quickHS,payloadsLVQuick,valsLVQuick)
    getPercentage(True,baseHS,payloadsLVBase,valsLVBase,damqHS, payloadsLVDamq, valsLVDamq)
    getPercentage(True,baseHS,payloadsLVBase,valsLVBase,combHS, payloadsLVComb, valsLVComb)
    getPercentage(True,baseHS,payloadsLVBase,valsLVBase,damrHS, payloadsLVDamr, valsLVDamr)
    getPercentage(True,baseHS,payloadsLVBase,valsLVBase,damaHS, payloadsLVDama, valsLVDama)
    getPercentage(True,baseHS,payloadsLVBase,valsLVBase,dampHS, payloadsLVDamp, valsLVDamp)
    getPercentage(True,baseHS,payloadsLVBase,valsLVBase,freeHS, payloadsLVFree, valsLVFree)
    getPercentage(True,combHS,payloadsLVComb,valsLVComb,freeHS, payloadsLVFree, valsLVFree)
    getPercentage(True,baseHS,payloadsLVBase,valsLVBase,onepHS, payloadsLVOnep, valsLVOnep)
    getPercentage(True,combHS,payloadsLVComb,valsLVComb,onepHS, payloadsLVOnep, valsLVOnep)
    # chained
    getPercentage(True,baseChHS,payloadsLVChBase,valsLVChBase,combChHS,payloadsLVChComb,valsLVChComb)

    print("Handle gain (basic versions):")
    # non-chained
    getPercentage(True,baseHS,payloadsHBase,valsHBase,cheapHS,payloadsHCheap,valsHCheap)
    getPercentage(True,baseHS,payloadsHBase,valsHBase,quickHS,payloadsHQuick,valsHQuick)
    getPercentage(True,baseHS,payloadsHBase,valsHBase,damqHS, payloadsHDamq, valsHDamq)
    getPercentage(True,baseHS,payloadsHBase,valsHBase,combHS, payloadsHComb, valsHComb)
    getPercentage(True,baseHS,payloadsHBase,valsHBase,damrHS, payloadsHDamr, valsHDamr)
    getPercentage(True,baseHS,payloadsHBase,valsHBase,damaHS, payloadsHDama, valsHDama)
    getPercentage(True,baseHS,payloadsHBase,valsHBase,dampHS, payloadsHDamp, valsHDamp)
    getPercentage(True,baseHS,payloadsHBase,valsHBase,freeHS, payloadsHFree, valsHFree)
    getPercentage(True,combHS,payloadsHComb,valsHComb,freeHS, payloadsHFree, valsHFree)
    getPercentage(True,baseHS,payloadsHBase,valsHBase,onepHS, payloadsHOnep, valsHOnep)
    getPercentage(True,combHS,payloadsHComb,valsHComb,onepHS, payloadsHOnep, valsHOnep)
    # chained
    getPercentage(True,baseChHS,payloadsHChBase,valsHChBase,combChHS,payloadsHChComb,valsHChComb)

    return (rateMbit,
            # throughput-view
            payloadsTVBase,   valsTVBase,   numsTVBase,
            payloadsTVCheap,  valsTVCheap,  numsTVCheap,
            payloadsTVQuick,  valsTVQuick,  numsTVQuick,
            payloadsTVDamq,   valsTVDamq,   numsTVDamq,
            payloadsTVComb,   valsTVComb,   numsTVComb,
            payloadsTVDamr,   valsTVDamr,   numsTVDamr,
            payloadsTVDama,   valsTVDama,   numsTVDama,
            payloadsTVDamp,   valsTVDamp,   numsTVDamp,
            payloadsTVFree,   valsTVFree,   numsTVFree,
            payloadsTVRoll,   valsTVRoll,   numsTVRoll,
            payloadsTVOnep,   valsTVOnep,   numsTVOnep,
            payloadsTVChBase, valsTVChBase, numsTVChBase,
            payloadsTVChComb, valsTVChComb, numsTVChComb,
            # latency-view
            payloadsLVBase,   valsLVBase,   numsLVBase,
            payloadsLVCheap,  valsLVCheap,  numsLVCheap,
            payloadsLVQuick,  valsLVQuick,  numsLVQuick,
            payloadsLVDamq,   valsLVDamq,   numsLVDamq,
            payloadsLVComb,   valsLVComb,   numsLVComb,
            payloadsLVDamr,   valsLVDamr,   numsLVDamr,
            payloadsLVDama,   valsLVDama,   numsLVDama,
            payloadsLVDamp,   valsLVDamp,   numsLVDamp,
            payloadsLVFree,   valsLVFree,   numsLVFree,
            payloadsLVRoll,   valsLVRoll,   numsLVRoll,
            payloadsLVOnep,   valsLVOnep,   numsLVOnep,
            payloadsLVChBase, valsLVChBase, numsLVChBase,
            payloadsLVChComb, valsLVChComb, numsLVChComb,
            # handle
            payloadsHBase,   valsHBase,   numsHBase,
            payloadsHCheap,  valsHCheap,  numsHCheap,
            payloadsHQuick,  valsHQuick,  numsHQuick,
            payloadsHDamq,   valsHDamq,   numsHDamq,
            payloadsHComb,   valsHComb,   numsHComb,
            payloadsHDamr,   valsHDamr,   numsHDamr,
            payloadsHDama,   valsHDama,   numsHDama,
            payloadsHDamp,   valsHDamp,   numsHDamp,
            payloadsHFree,   valsHFree,   numsHFree,
            payloadsHRoll,   valsHRoll,   numsHRoll,
            payloadsHOnep,   valsHOnep,   numsHOnep,
            payloadsHChBase, valsHChBase, numsHChBase,
            payloadsHChComb, valsHChComb, numsHChComb,
            # crypto-sign
            payloadsCSBase,   valsCSBase,   numsCSBase,
            payloadsCSCheap,  valsCSCheap,  numsCSCheap,
            payloadsCSQuick,  valsCSQuick,  numsCSQuick,
            payloadsCSDamq,   valsCSDamq,   numsCSDamq,
            payloadsCSComb,   valsCSComb,   numsCSComb,
            payloadsCSDamr,   valsCSDamr,   numsCSDamr,
            payloadsCSDama,   valsCSDama,   numsCSDama,
            payloadsCSDamp,   valsCSDamp,   numsCSDamp,
            payloadsCSFree,   valsCSFree,   numsCSFree,
            payloadsCSRoll,   valsCSRoll,   numsCSRoll,
            payloadsCSOnep,   valsCSOnep,   numsCSOnep,
            payloadsCSChBase, valsCSChBase, numsCSChBase,
            payloadsCSChComb, valsCSChComb, numsCSChComb,
            # crypto-verif
            payloadsCVBase,   valsCVBase,   numsCVBase,
            payloadsCVCheap,  valsCVCheap,  numsCVCheap,
            payloadsCVQuick,  valsCVQuick,  numsCVQuick,
            payloadsCVDamq,   valsCVDamq,   numsCVDamq,
            payloadsCVComb,   valsCVComb,   numsCVComb,
            payloadsCVDamr,   valsCVDamr,   numsCVDamr,
            payloadsCVDama,   valsCVDama,   numsCVDama,
            payloadsCVDamp,   valsCVDamp,   numsCVDamp,
            payloadsCVFree,   valsCVFree,   numsCVFree,
            payloadsCVRoll,   valsCVRoll,   numsCVRoll,
            payloadsCVOnep,   valsCVOnep,   numsCVOnep,
            payloadsCVChBase, valsCVChBase, numsCVChBase,
            payloadsCVChComb, valsCVChComb, numsCVChComb)
## End of createPlotPayloadAux



def createPlotPayload(files):
    LW = 1 # linewidth
    MS = 5 # markersize
    XYT = (0,5)

    #plt.figure(figsize=(2, 6))
    #, dpi=80)

    global plotThroughput
    global plotLatency

    global baseCOL
    global cheapCOL
    global quickCOL
    global damqCOL
    global combCOL
    global damrCOL
    global damaCOL
    global dampCOL
    global freeCOL
    global rollCOL
    global onepCOL
    global onepbCOL
    global onepcCOL
    global onepdCOL
    global baseChCOL
    global combChCOL

    if (plotHandle or plotCrypto) and not plotView:
        plotThroughput = False
        plotLatency    = True

    numPlots=2
    if (plotThroughput and not plotLatency) or (not plotThroughput and plotLatency):
        numPlots=1

    ## Plotting
    print("plotting",numPlots,"plot(s)")
    fig, axs = plt.subplots(numPlots,1)
    if numPlots == 1:
        x = axs
        axs = [x]
    #,figsize=(4, 10)
    if showTitle:
        if debugPlot:
            info = "file="+pFile
            info += "; cpus="+str(dockerCpu)
            info += "; mem="+str(dockerMem)
            info += "; lat="+str(networkLat)
            info += "; payload="+str(payloadSize)
            info += "; repeats1="+str(repeats)
            info += "; repeats2="+str(repeatsL2)
            info += "; #views="+str(numViews)
            info += "; regions="+regions[0]
            if plotHandle and not plotView:
                fig.suptitle("Handling time\n("+info+")")
            else:
                fig.suptitle("Throughputs (top) & Latencies (bottom)\n("+info+")")
        else:
            if plotHandle and not plotView:
                fig.suptitle("Handling time")
#            else:
#                fig.suptitle("Throughputs (top) & Latencies (bottom)")

    adjustFigAspect(fig,aspect=0.9)
    #adjustFigAspect(fig,aspect=0.9)
    if numPlots == 2:
        fig.set_figheight(6)
    else: # == 1
        fig.set_figheight(3)
    #fig.set_figwidth(4)

    width = 20

    if plotThroughput:
        # naming the x/y axis
        #axs[0].set(xlabel="payload size", ylabel="throughput")
        if showYlabel:
            axs[0].set(ylabel="throughput (Kops/s)")
        if logScale:
            axs[0].set_yscale('log')
        if whichExp == "EUexp1":
            axs[0].set_yticks((0.5,1,10,20,70))
            axs[0].set_ylim([0.5,70])
            axs[0].get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        elif whichExp == "ALLexp1":
            axs[0].set_yticks((0.3,1,6))
            axs[0].set_ylim([0.3,6])
            axs[0].get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        # giving a title to my graph
        #axs[0].set_title("throughputs")
        # plotting the points

        posL = 0
        posT = 0

        for file in files:
            (rate,
             # throughput-view
             payloadsTVBase,   valsTVBase,   numsTVBase,
             payloadsTVCheap,  valsTVCheap,  numsTVCheap,
             payloadsTVQuick,  valsTVQuick,  numsTVQuick,
             payloadsTVDamq,   valsTVDamq,   numsTVDamq,
             payloadsTVComb,   valsTVComb,   numsTVComb,
             payloadsTVDamr,   valsTVDamr,   numsTVDamr,
             payloadsTVDama,   valsTVDama,   numsTVDama,
             payloadsTVDamp,   valsTVDamp,   numsTVDamp,
             payloadsTVFree,   valsTVFree,   numsTVFree,
             payloadsTVRoll,   valsTVRoll,   numsTVRoll,
             payloadsTVOnep,   valsTVOnep,   numsTVOnep,
             payloadsTVChBase, valsTVChBase, numsTVChBase,
             payloadsTVChComb, valsTVChComb, numsTVChComb,
             # latency-view
             payloadsLVBase,   valsLVBase,   numsLVBase,
             payloadsLVCheap,  valsLVCheap,  numsLVCheap,
             payloadsLVQuick,  valsLVQuick,  numsLVQuick,
             payloadsLVDamq,   valsLVDamq,   numsLVDamq,
             payloadsLVComb,   valsLVComb,   numsLVComb,
             payloadsLVDamr,   valsLVDamr,   numsLVDamr,
             payloadsLVDama,   valsLVDama,   numsLVDama,
             payloadsLVDamp,   valsLVDamp,   numsLVDamp,
             payloadsLVFree,   valsLVFree,   numsLVFree,
             payloadsLVRoll,   valsLVRoll,   numsLVRoll,
             payloadsLVOnep,   valsLVOnep,   numsLVOnep,
             payloadsLVChBase, valsLVChBase, numsLVChBase,
             payloadsLVChComb, valsLVChComb, numsLVChComb,
             # handle
             payloadsHBase,   valsHBase,   numsHBase,
             payloadsHCheap,  valsHCheap,  numsHCheap,
             payloadsHQuick,  valsHQuick,  numsHQuick,
             payloadsHDamq,   valsHDamq,   numsHDamq,
             payloadsHComb,   valsHComb,   numsHComb,
             payloadsHDamr,   valsHDamr,   numsHDamr,
             payloadsHDama,   valsHDama,   numsHDama,
             payloadsHDamp,   valsHDamp,   numsHDamp,
             payloadsHFree,   valsHFree,   numsHFree,
             payloadsHRoll,   valsHRoll,   numsHRoll,
             payloadsHOnep,   valsHOnep,   numsHOnep,
             payloadsHChBase, valsHChBase, numsHChBase,
             payloadsHChComb, valsHChComb, numsHChComb,
             # crypto-sign
             payloadsCSBase,   valsCSBase,   numsCSBase,
             payloadsCSCheap,  valsCSCheap,  numsCSCheap,
             payloadsCSQuick,  valsCSQuick,  numsCSQuick,
             payloadsCSDamq,   valsCSDamq,   numsCSDamq,
             payloadsCSComb,   valsCSComb,   numsCSComb,
             payloadsCSDamr,   valsCSDamr,   numsCSDamr,
             payloadsCSDama,   valsCSDama,   numsCSDama,
             payloadsCSDamp,   valsCSDamp,   numsCSDamp,
             payloadsCSFree,   valsCSFree,   numsCSFree,
             payloadsCSRoll,   valsCSRoll,   numsCSRoll,
             payloadsCSOnep,   valsCSOnep,   numsCSOnep,
             payloadsCSChBase, valsCSChBase, numsCSChBase,
             payloadsCSChComb, valsCSChComb, numsCSChComb,
             # crypto-verif
             payloadsCVBase,   valsCVBase,   numsCVBase,
             payloadsCVCheap,  valsCVCheap,  numsCVCheap,
             payloadsCVQuick,  valsCVQuick,  numsCVQuick,
             payloadsCVDamq,   valsCVDamq,   numsCVDamq,
             payloadsCVComb,   valsCVComb,   numsCVComb,
             payloadsCVDamr,   valsCVDamr,   numsCVDamr,
             payloadsCVDama,   valsCVDama,   numsCVDama,
             payloadsCVDamp,   valsCVDamp,   numsCVDamp,
             payloadsCVFree,   valsCVFree,   numsCVFree,
             payloadsCVRoll,   valsCVRoll,   numsCVRoll,
             payloadsCVOnep,   valsCVOnep,   numsCVOnep,
             payloadsCVChBase, valsCVChBase, numsCVChBase,
             payloadsCVChComb, valsCVChComb, numsCVChComb) = createPlotPayloadAux(file)

            if rate == 10:
                baseCOL = "black"
                combCOL = "red"
            if rate == 100:
                baseCOL = "orange"
                combCOL = "blue"
            if rate == 1000:
                baseCOL = "purple"
                combCOL = "green"

            # axs[0].bar(8, 0.22, width=10)
            # axs[0].bar(128, 0.22, width=10)
            # axs[0].bar(1024, 0.22, width=10)

            #axs[0].set_xticklabels([str(x) for x in payloadsTVBase])

            if plotView:
                if plotBasic:
                    if runBase and len(payloadsTVBase) > 0:
                        if barPlot:
                            payloadsTVBase2 = [x+posT for x in payloadsTVBase]
                            axs[0].bar(payloadsTVBase2, valsTVBase, width=width,   color=baseCOL,   linewidth=LW, linestyle=baseLS,   label=baseHS + "(" + str(int(rate)) + ")")
                            posT += width
                            for (i,j) in zip(payloadsTVBase, valsTVBase):
                                f = open("points","a")
                                f.write("throughput " + str(int(rate)) + " " + str(i) + " " + str(j) + "\n")
                                f.close()
                        else:
                            axs[0].plot(payloadsTVBase,   valsTVBase,   color=baseCOL,   linewidth=LW, marker=baseMRK,   markersize=MS, linestyle=baseLS,   label=baseHS + "(" + str(int(rate)) + ")")
                    if len(payloadsTVCheap) > 0:
                        axs[0].plot(payloadsTVCheap,  valsTVCheap,  color=cheapCOL,  linewidth=LW, marker=cheapMRK,  markersize=MS, linestyle=cheapLS,  label=cheapHS + "(" + str(int(rate)) + ")")
                    if len(payloadsTVQuick) > 0:
                        axs[0].plot(payloadsTVQuick,  valsTVQuick,  color=quickCOL,  linewidth=LW, marker=quickMRK,  markersize=MS, linestyle=quickLS,  label=quickHS + "(" + str(int(rate)) + ")")
                    if len(payloadsTVDamq) > 0:
                        axs[0].plot(payloadsTVDamq,  valsTVDamq,  color=damqCOL,  linewidth=LW, marker=damqMRK,  markersize=MS, linestyle=damqLS,  label=damqHS + "(" + str(int(rate)) + ")")
                    if runComb and len(payloadsTVComb) > 0:
                        if barPlot:
                            payloadsTVComb = [x+posT for x in payloadsTVComb]
                            axs[0].bar(payloadsTVComb,   valsTVComb, width=width,   color=combCOL,   linewidth=LW, linestyle=combLS,   label=combHS + "(" + str(int(rate)) + ")")
                            posT += width
                            for (i,j) in zip(payloadsTVComb, valsTVComb):
                                f = open("points","a")
                                f.write("throughput " + str(int(rate)) + " " + str(i) + " " + str(j) + "\n")
                                f.close()
                        else:
                            axs[0].plot(payloadsTVComb,   valsTVComb,   color=combCOL,   linewidth=LW, marker=combMRK,   markersize=MS, linestyle=combLS,   label=combHS + "(" + str(int(rate)) + ")")
                    if runDamr and len(payloadsTVDamr) > 0:
                        if barPlot:
                            payloadsTVDamr = [x+posT for x in payloadsTVDamr]
                            axs[0].bar(payloadsTVDamr,   valsTVDamr, width=width,   color=damrCOL,   linewidth=LW, linestyle=damrLS,   label=damrHS + "(" + str(int(rate)) + ")")
                            posT += width
                            for (i,j) in zip(payloadsTVDamr, valsTVDamr):
                                f = open("points","a")
                                f.write("throughput " + str(int(rate)) + " " + str(i) + " " + str(j) + "\n")
                                f.close()
                        else:
                            axs[0].plot(payloadsTVDamr,   valsTVDamr,   color=damrCOL,   linewidth=LW, marker=damrMRK,   markersize=MS, linestyle=damrLS,   label=damrHS + "(" + str(int(rate)) + ")")
                    if runDama and len(payloadsTVDama) > 0:
                        if barPlot:
                            payloadsTVDama = [x+posT for x in payloadsTVDama]
                            axs[0].bar(payloadsTVDama,   valsTVDama, width=width,   color=damaCOL,   linewidth=LW, linestyle=damaLS,   label=damaHS + "(" + str(int(rate)) + ")")
                            posT += width
                            for (i,j) in zip(payloadsTVDama, valsTVDama):
                                f = open("points","a")
                                f.write("throughput " + str(int(rate)) + " " + str(i) + " " + str(j) + "\n")
                                f.close()
                        else:
                            axs[0].plot(payloadsTVDama,   valsTVDama,   color=damaCOL,   linewidth=LW, marker=damaMRK,   markersize=MS, linestyle=damaLS,   label=damaHS + "(" + str(int(rate)) + ")")
                    if runDamp and len(payloadsTVDamp) > 0:
                        if barPlot:
                            payloadsTVDamp = [x+posT for x in payloadsTVDamp]
                            axs[0].bar(payloadsTVDamp,   valsTVDamp, width=width,   color=dampCOL,   linewidth=LW, linestyle=dampLS,   label=dampHS + "(" + str(int(rate)) + ")")
                            posT += width
                            for (i,j) in zip(payloadsTVDmr, valsTVDamp):
                                f = open("points","a")
                                f.write("throughput " + str(int(rate)) + " " + str(i) + " " + str(j) + "\n")
                                f.close()
                        else:
                            axs[0].plot(payloadsTVDamp,   valsTVDamp,   color=dampCOL,   linewidth=LW, marker=dampMRK,   markersize=MS, linestyle=dampLS,   label=dampHS + "(" + str(int(rate)) + ")")
                    if len(payloadsTVFree) > 0:
                        axs[0].plot(payloadsTVFree,   valsTVFree,   color=freeCOL,   linewidth=LW, marker=freeMRK,   markersize=MS, linestyle=freeLS,   label=freeHS + "(" + str(int(rate)) + ")")
                    if len(payloadsTVRoll) > 0:
                        axs[0].plot(payloadsTVRoll,   valsTVRoll,   color=rollCOL,   linewidth=LW, marker=rollMRK,   markersize=MS, linestyle=rollLS,   label=rollHS + "(" + str(int(rate)) + ")")
                    if len(payloadsTVOnep) > 0:
                        axs[0].plot(payloadsTVOnep,   valsTVOnep,   color=onepCOL,   linewidth=LW, marker=onepMRK,   markersize=MS, linestyle=onepLS,   label=onepHS + "(" + str(int(rate)) + ")")
                if plotChained:
                    if len(payloadsTVChBase) > 0:
                        axs[0].plot(payloadsTVChBase, valsTVChBase, color=baseChCOL, linewidth=LW, marker=baseChMRK, markersize=MS, linestyle=baseChLS, label=baseChHS + "(" + str(int(rate)) + ")")
                    if len(payloadsTVChComb) > 0:
                        axs[0].plot(payloadsTVChComb, valsTVChComb, color=combChCOL, linewidth=LW, marker=combChMRK, markersize=MS, linestyle=combChLS, label=combChHS + "(" + str(int(rate)) + ")")
                if debugPlot:
                    if plotBasic:
                        for x,y,z in zip(payloadsTVBase, valsTVBase, numsTVBase):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsTVCheap, valsTVCheap, numsTVCheap):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsTVQuick, valsTVQuick, numsTVQuick):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsTVDamq, valsTVDamq, numsTVDamq):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsTVComb, valsTVComb, numsTVComb):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsTVDamr, valsTVDamr, numsTVDamr):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsTVDama, valsTVDama, numsTVDama):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsTVDamp, valsTVDamp, numsTVDamp):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsTVFree, valsTVFree, numsTVFree):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsTVRoll, valsTVRoll, numsTVRoll):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsTVOnep, valsTVOnep, numsTVOnep):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    if plotChained:
                        for x,y,z in zip(payloadsTVChBase, valsTVChBase, numsTVChBase):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsTVChComb, valsTVChComb, numsTVChComb):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')

        # legend
        if showLegend1:
            axs[0].legend(ncol=2,prop={'size': 9})

    if plotLatency:
        ax=axs[0]
        if plotThroughput:
            ax=axs[1]
        # naming the x/y axis
        if showYlabel:
            if plotHandle and not plotView:
                ax.set(xlabel="payload size", ylabel="handling time (ms)")
            else:
                ax.set(xlabel="payload size", ylabel="latency (ms)")
        else:
            ax.set(xlabel="payload size")
        if logScale:
            ax.set_yscale('log')
        if whichExp == "EUexp1":
            ax.set_yticks((5,100,600))
            ax.set_ylim([5,600])
            ax.get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        elif whichExp == "ALLexp1":
            ax.set_yticks((60,100,1000))
            ax.set_ylim([60,1000])
            ax.get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        # giving a title to my graph
        #ax.set_title("latencies")
        # plotting the points

        for file in files:
            (rate,
             # throughput-view
             payloadsTVBase,   valsTVBase,   numsTVBase,
             payloadsTVCheap,  valsTVCheap,  numsTVCheap,
             payloadsTVQuick,  valsTVQuick,  numsTVQuick,
             payloadsTVDamq,   valsTVDamq,   numsTVDamq,
             payloadsTVComb,   valsTVComb,   numsTVComb,
             payloadsTVDamr,   valsTVDamr,   numsTVDamr,
             payloadsTVDama,   valsTVDama,   numsTVDama,
             payloadsTVDamp,   valsTVDamp,   numsTVDamp,
             payloadsTVFree,   valsTVFree,   numsTVFree,
             payloadsTVRoll,   valsTVRoll,   numsTVRoll,
             payloadsTVOnep,   valsTVOnep,   numsTVOnep,
             payloadsTVChBase, valsTVChBase, numsTVChBase,
             payloadsTVChComb, valsTVChComb, numsTVChComb,
             # latency-view
             payloadsLVBase,   valsLVBase,   numsLVBase,
             payloadsLVCheap,  valsLVCheap,  numsLVCheap,
             payloadsLVQuick,  valsLVQuick,  numsLVQuick,
             payloadsLVDamq,   valsLVDamq,   numsLVDamq,
             payloadsLVComb,   valsLVComb,   numsLVComb,
             payloadsLVDamr,   valsLVDamr,   numsLVDamr,
             payloadsLVDama,   valsLVDama,   numsLVDama,
             payloadsLVDamp,   valsLVDamp,   numsLVDamp,
             payloadsLVFree,   valsLVFree,   numsLVFree,
             payloadsLVRoll,   valsLVRoll,   numsLVRoll,
             payloadsLVOnep,   valsLVOnep,   numsLVOnep,
             payloadsLVChBase, valsLVChBase, numsLVChBase,
             payloadsLVChComb, valsLVChComb, numsLVChComb,
             # handle
             payloadsHBase,   valsHBase,   numsHBase,
             payloadsHCheap,  valsHCheap,  numsHCheap,
             payloadsHQuick,  valsHQuick,  numsHQuick,
             payloadsHDamq,   valsHDamq,   numsHDamq,
             payloadsHComb,   valsHComb,   numsHComb,
             payloadsHDamr,   valsHDamr,   numsHDamr,
             payloadsHDama,   valsHDama,   numsHDama,
             payloadsHDamp,   valsHDamp,   numsHDamp,
             payloadsHFree,   valsHFree,   numsHFree,
             payloadsHRoll,   valsHRoll,   numsHRoll,
             payloadsHOnep,   valsHOnep,   numsHOnep,
             payloadsHChBase, valsHChBase, numsHChBase,
             payloadsHChComb, valsHChComb, numsHChComb,
             # crypto-sign
             payloadsCSBase,   valsCSBase,   numsCSBase,
             payloadsCSCheap,  valsCSCheap,  numsCSCheap,
             payloadsCSQuick,  valsCSQuick,  numsCSQuick,
             payloadsCSDamq,   valsCSDamq,   numsCSDamq,
             payloadsCSComb,   valsCSComb,   numsCSComb,
             payloadsCSDamr,   valsCSDamr,   numsCSDamr,
             payloadsCSDama,   valsCSDama,   numsCSDama,
             payloadsCSDamp,   valsCSDamp,   numsCSDamp,
             payloadsCSFree,   valsCSFree,   numsCSFree,
             payloadsCSRoll,   valsCSRoll,   numsCSRoll,
             payloadsCSOnep,   valsCSOnep,   numsCSOnep,
             payloadsCSChBase, valsCSChBase, numsCSChBase,
             payloadsCSChComb, valsCSChComb, numsCSChComb,
             # crypto-verif
             payloadsCVBase,   valsCVBase,   numsCVBase,
             payloadsCVCheap,  valsCVCheap,  numsCVCheap,
             payloadsCVQuick,  valsCVQuick,  numsCVQuick,
             payloadsCVDamq,   valsCVDamq,   numsCVDamq,
             payloadsCVComb,   valsCVComb,   numsCVComb,
             payloadsCVDamr,   valsCVDamr,   numsCVDamr,
             payloadsCVDama,   valsCVDama,   numsCVDama,
             payloadsCVDamp,   valsCVDamp,   numsCVDamp,
             payloadsCVFree,   valsCVFree,   numsCVFree,
             payloadsCVRoll,   valsCVRoll,   numsCVRoll,
             payloadsCVOnep,   valsCVOnep,   numsCVOnep,
             payloadsCVChBase, valsCVChBase, numsCVChBase,
             payloadsCVChComb, valsCVChComb, numsCVChComb) = createPlotPayloadAux(file)

            if rate == 10:
                baseCOL = "black"
                combCOL = "red"
            if rate == 100:
                baseCOL = "orange"
                combCOL = "blue"
            if rate == 1000:
                baseCOL = "purple"
                combCOL = "green"

            if plotView:
                if plotBasic:
                    if runBase and len(payloadsLVBase) > 0:
                        if barPlot:
                            payloadsLVBase2 = [x+posL for x in payloadsLVBase]
                            ax.bar(payloadsLVBase2,   valsLVBase, width=width,   color=baseCOL,   linewidth=LW, linestyle=baseLS,   label=baseHS + "(" + str(int(rate)) + ")")
                            posL += width
                            for (i,j) in zip(payloadsLVBase, valsLVBase):
                                f = open("points","a")
                                f.write("latency " + str(int(rate)) + " " + str(i) + " " + str(j) + "\n")
                                f.close()
                        else:
                            ax.plot(payloadsLVBase,   valsLVBase,   color=baseCOL,   linewidth=LW, marker=baseMRK,   markersize=MS, linestyle=baseLS,   label=baseHS + "(" + str(int(rate)) + ")")
                    if len(payloadsLVCheap) > 0:
                        ax.plot(payloadsLVCheap,  valsLVCheap,  color=cheapCOL,  linewidth=LW, marker=cheapMRK,  markersize=MS, linestyle=cheapLS,  label=cheapHS + "(" + str(int(rate)) + ")")
                    if len(payloadsLVQuick) > 0:
                        ax.plot(payloadsLVQuick,  valsLVQuick,  color=quickCOL,  linewidth=LW, marker=quickMRK,  markersize=MS, linestyle=quickLS,  label=quickHS + "(" + str(int(rate)) + ")")
                    if len(payloadsLVDamq) > 0:
                        ax.plot(payloadsLVDamq,  valsLVDamq,  color=damqCOL,  linewidth=LW, marker=damqMRK,  markersize=MS, linestyle=damqLS,  label=damqHS + "(" + str(int(rate)) + ")")
                    if runComb and len(payloadsLVComb) > 0:
                        if barPlot:
                            payloadsLVComb = [x+posL for x in payloadsLVComb]
                            ax.bar(payloadsLVComb,   valsLVComb, width=width,   color=combCOL,   linewidth=LW, linestyle=combLS,   label=combHS + "(" + str(int(rate)) + ")")
                            posL += width
                            for (i,j) in zip(payloadsLVComb, valsLVComb):
                                f = open("points","a")
                                f.write("latency " + str(int(rate)) + " " + str(i) + " " + str(j) + "\n")
                                f.close()
                        else:
                            ax.plot(payloadsLVComb,   valsLVComb,   color=combCOL,   linewidth=LW, marker=combMRK,   markersize=MS, linestyle=combLS,   label=combHS + "(" + str(int(rate)) + ")")
                    if runDamr and len(payloadsLVDamr) > 0:
                        if barPlot:
                            payloadsLVDamr = [x+posL for x in payloadsLVDamr]
                            ax.bar(payloadsLVDamr,   valsLVDamr, width=width,   color=damrCOL,   linewidth=LW, linestyle=damrLS,   label=damrHS + "(" + str(int(rate)) + ")")
                            posL += width
                            for (i,j) in zip(payloadsLVDamr, valsLVDamr):
                                f = open("points","a")
                                f.write("latency " + str(int(rate)) + " " + str(i) + " " + str(j) + "\n")
                                f.close()
                        else:
                            ax.plot(payloadsLVDamr,   valsLVDamr,   color=damrCOL,   linewidth=LW, marker=damrMRK,   markersize=MS, linestyle=damrLS,   label=damrHS + "(" + str(int(rate)) + ")")
                    if runDama and len(payloadsLVDama) > 0:
                        if barPlot:
                            payloadsLVDama = [x+posL for x in payloadsLVDama]
                            ax.bar(payloadsLVDama,   valsLVDama, width=width,   color=damaCOL,   linewidth=LW, linestyle=damaLS,   label=damaHS + "(" + str(int(rate)) + ")")
                            posL += width
                            for (i,j) in zip(payloadsLVDama, valsLVDama):
                                f = open("points","a")
                                f.write("latency " + str(int(rate)) + " " + str(i) + " " + str(j) + "\n")
                                f.close()
                        else:
                            ax.plot(payloadsLVDama,   valsLVDama,   color=damaCOL,   linewidth=LW, marker=damaMRK,   markersize=MS, linestyle=damaLS,   label=damaHS + "(" + str(int(rate)) + ")")
                    if runDamp and len(payloadsLVDamp) > 0:
                        if barPlot:
                            payloadsLVDamp = [x+posL for x in payloadsLVDamp]
                            ax.bar(payloadsLVDamp,   valsLVDamp, width=width,   color=dampCOL,   linewidth=LW, linestyle=dampLS,   label=dampHS + "(" + str(int(rate)) + ")")
                            posL += width
                            for (i,j) in zip(payloadsLVDamp, valsLVDamp):
                                f = open("points","a")
                                f.write("latency " + str(int(rate)) + " " + str(i) + " " + str(j) + "\n")
                                f.close()
                        else:
                            ax.plot(payloadsLVDamp,   valsLVDamp,   color=dampCOL,   linewidth=LW, marker=dampMRK,   markersize=MS, linestyle=dampLS,   label=dampHS + "(" + str(int(rate)) + ")")
                    if len(payloadsLVFree) > 0:
                        ax.plot(payloadsLVFree,   valsLVFree,   color=freeCOL,   linewidth=LW, marker=freeMRK,   markersize=MS, linestyle=freeLS,   label=freeHS + "(" + str(int(rate)) + ")")
                    if len(payloadsLVRoll) > 0:
                        ax.plot(payloadsLVRoll,   valsLVRoll,   color=rollCOL,   linewidth=LW, marker=rollMRK,   markersize=MS, linestyle=rollLS,   label=rollHS + "(" + str(int(rate)) + ")")
                    if len(payloadsLVOnep) > 0:
                        ax.plot(payloadsLVOnep,   valsLVOnep,   color=onepCOL,   linewidth=LW, marker=onepMRK,   markersize=MS, linestyle=onepLS,   label=onepHS + "(" + str(int(rate)) + ")")
                if plotChained:
                    if len(payloadsLVChBase) > 0:
                        ax.plot(payloadsLVChBase, valsLVChBase, color=baseChCOL, linewidth=LW, marker=baseChMRK, markersize=MS, linestyle=baseChLS, label=baseChHS + "(" + str(int(rate)) + ")")
                    if len(payloadsLVChComb) > 0:
                        ax.plot(payloadsLVChComb, valsLVChComb, color=combChCOL, linewidth=LW, marker=combChMRK, markersize=MS, linestyle=combChLS, label=combChHS + "(" + str(int(rate)) + ")")
                if debugPlot:
                    if plotBasic:
                        for x,y,z in zip(payloadsLVBase, valsLVBase, numsLVBase):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsLVCheap, valsLVCheap, numsLVCheap):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsLVQuick, valsLVQuick, numsLVQuick):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsLVDamq, valsLVDamq, numsLVDamq):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsLVComb, valsLVComb, numsLVComb):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsLVDamr, valsLVDamr, numsLVDamr):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsLVDama, valsLVDama, numsLVDama):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsLVDamp, valsLVDamp, numsLVDamp):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsLVFree, valsLVFree, numsLVFree):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsLVRoll, valsLVRoll, numsLVRoll):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsLVOnep, valsLVOnep, numsLVOnep):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    if plotChained:
                        for x,y,z in zip(payloadsLVChBase, valsLVChBase, numsLVChBase):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsLVChComb, valsLVChComb, numsLVChComb):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
            if plotHandle:
                if plotBasic:
                    if len(payloadsHBase) > 0:
                        ax.plot(payloadsHBase,   valsHBase,   color=baseCOL,   linewidth=LW, marker="+", markersize=MS, linestyle=baseLS,   label=baseHS + "(" + str(int(rate)) + ")"+"")
                    if len(payloadsHCheap) > 0:
                        ax.plot(payloadsHCheap,  valsHCheap,  color=cheapCOL,  linewidth=LW, marker="+", markersize=MS, linestyle=cheapLS,  label=cheapHS + "(" + str(int(rate)) + ")"+"")
                    if len(payloadsHQuick) > 0:
                        ax.plot(payloadsHQuick,  valsHQuick,  color=quickCOL,  linewidth=LW, marker="+", markersize=MS, linestyle=quickLS,  label=quickHS + "(" + str(int(rate)) + ")"+"")
                    if len(payloadsHDamq) > 0:
                        ax.plot(payloadsHDamq,   valsHDamq,   color=damqCOL,   linewidth=LW, marker="+", markersize=MS, linestyle=damqLS,   label=damqHS + "(" + str(int(rate)) + ")"+"")
                    if len(payloadsHComb) > 0:
                        ax.plot(payloadsHComb,   valsHComb,   color=combCOL,   linewidth=LW, marker="+", markersize=MS, linestyle=combLS,   label=combHS + "(" + str(int(rate)) + ")"+"")
                    if len(payloadsHDamr) > 0:
                        ax.plot(payloadsHDamr,   valsHDamr,   color=damrCOL,   linewidth=LW, marker="+", markersize=MS, linestyle=damrLS,   label=damrHS + "(" + str(int(rate)) + ")"+"")
                    if len(payloadsHDama) > 0:
                        ax.plot(payloadsHDama,   valsHDama,   color=damaCOL,   linewidth=LW, marker="+", markersize=MS, linestyle=damaLS,   label=damaHS + "(" + str(int(rate)) + ")"+"")
                    if len(payloadsHDamp) > 0:
                        ax.plot(payloadsHDamp,   valsHDamp,   color=dampCOL,   linewidth=LW, marker="+", markersize=MS, linestyle=dampLS,   label=dampHS + "(" + str(int(rate)) + ")"+"")
                    if len(payloadsHFree) > 0:
                        ax.plot(payloadsHFree,   valsHFree,   color=freeCOL,   linewidth=LW, marker="+", markersize=MS, linestyle=freeLS,   label=freeHS + "(" + str(int(rate)) + ")"+"")
                    if len(payloadsHRoll) > 0:
                        ax.plot(payloadsHRoll,   valsHRoll,   color=rollCOL,   linewidth=LW, marker="+", markersize=MS, linestyle=rollLS,   label=rollHS + "(" + str(int(rate)) + ")"+"")
                    if len(payloadsHOnep) > 0:
                        ax.plot(payloadsHOnep,   valsHOnep,   color=onepCOL,   linewidth=LW, marker="+", markersize=MS, linestyle=onepLS,   label=onepHS + "(" + str(int(rate)) + ")"+"")
                if plotChained:
                    if len(payloadsHChBase) > 0:
                        ax.plot(payloadsHChBase, valsHChBase, color=baseChCOL, linewidth=LW, marker="+", markersize=MS, linestyle=baseChLS, label=baseChHS + "(" + str(int(rate)) + ")"+"")
                    if len(payloadsHChComb) > 0:
                        ax.plot(payloadsHChComb, valsHChComb, color=combChCOL, linewidth=LW, marker="+", markersize=MS, linestyle=combChLS, label=combChHS + "(" + str(int(rate)) + ")"+"")
                if debugPlot:
                    if plotBasic:
                        for x,y,z in zip(payloadsHBase, valsHBase, numsHBase):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsHCheap, valsHCheap, numsHCheap):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsHQuick, valsHQuick, numsHQuick):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsHDamq, valsHDamq, numsHDamq):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsHComb, valsHComb, numsHComb):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsHDamr, valsHDamr, numsHDamr):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsHDama, valsHDama, numsHDama):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsHDamp, valsHDamp, numsHDamp):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsHFree, valsHFree, numsHFree):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsHRoll, valsHRoll, numsHRoll):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsHOnep, valsHOnep, numsHOnep):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    if plotChained:
                        for x,y,z in zip(payloadsHChBase, valsHChBase, numsHChBase):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsHChComb, valsHChComb, numsHChComb):
                            ax.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
            if plotCrypto: # Sign
                if plotBasic:
                    if len(payloadsCSBase) > 0:
                        axs[0].plot(payloadsCSBase,   valsCSBase,   color=baseCOL,   linewidth=LW, marker="1", markersize=MS, linestyle=baseLS,   label=baseHS + "(" + str(int(rate)) + ")"+" (crypto-sign)")
                    if len(payloadsCSCheap) > 0:
                        axs[0].plot(payloadsCSCheap,  valsCSCheap,  color=cheapCOL,  linewidth=LW, marker="1", markersize=MS, linestyle=cheapLS,  label=cheapHS + "(" + str(int(rate)) + ")"+" (crypto-sign)")
                    if len(payloadsCSQuick) > 0:
                        axs[0].plot(payloadsCSQuick,  valsCSQuick,  color=quickCOL,  linewidth=LW, marker="1", markersize=MS, linestyle=quickLS,  label=quickHS + "(" + str(int(rate)) + ")"+" (crypto-sign)")
                    if len(payloadsCSDamq) > 0:
                        axs[0].plot(payloadsCSDamq,   valsCSDamq,   color=damqCOL,   linewidth=LW, marker="1", markersize=MS, linestyle=damqLS,   label=damqHS + "(" + str(int(rate)) + ")"+" (crypto-sign)")
                    if len(payloadsCSComb) > 0:
                        axs[0].plot(payloadsCSComb,   valsCSComb,   color=combCOL,   linewidth=LW, marker="1", markersize=MS, linestyle=combLS,   label=combHS + "(" + str(int(rate)) + ")"+" (crypto-sign)")
                    if len(payloadsCSDamr) > 0:
                        axs[0].plot(payloadsCSDamr,   valsCSDamr,   color=damrCOL,   linewidth=LW, marker="1", markersize=MS, linestyle=damrLS,   label=damrHS + "(" + str(int(rate)) + ")"+" (crypto-sign)")
                    if len(payloadsCSDama) > 0:
                        axs[0].plot(payloadsCSDama,   valsCSDama,   color=damaCOL,   linewidth=LW, marker="1", markersize=MS, linestyle=damaLS,   label=damaHS + "(" + str(int(rate)) + ")"+" (crypto-sign)")
                    if len(payloadsCSDamp) > 0:
                        axs[0].plot(payloadsCSDamp,   valsCSDamp,   color=dampCOL,   linewidth=LW, marker="1", markersize=MS, linestyle=dampLS,   label=dampHS + "(" + str(int(rate)) + ")"+" (crypto-sign)")
                    if len(payloadsCSFree) > 0:
                        axs[0].plot(payloadsCSFree,   valsCSFree,   color=freeCOL,   linewidth=LW, marker="1", markersize=MS, linestyle=freeLS,   label=freeHS + "(" + str(int(rate)) + ")"+" (crypto-sign)")
                    if len(payloadsCSRoll) > 0:
                        axs[0].plot(payloadsCSRoll,   valsCSRoll,   color=rollCOL,   linewidth=LW, marker="1", markersize=MS, linestyle=rollLS,   label=rollHS + "(" + str(int(rate)) + ")"+" (crypto-sign)")
                    if len(payloadsCSOnep) > 0:
                        axs[0].plot(payloadsCSOnep,   valsCSOnep,   color=onepCOL,   linewidth=LW, marker="1", markersize=MS, linestyle=onepLS,   label=onepHS + "(" + str(int(rate)) + ")"+" (crypto-sign)")
                if plotChained:
                    if len(payloadsCSChBase) > 0:
                        axs[0].plot(payloadsCSChBase, valsCSChBase, color=baseChCOL, linewidth=LW, marker="1", markersize=MS, linestyle=baseChLS, label=baseChHS + "(" + str(int(rate)) + ")"+" (crypto-sign)")
                    if len(payloadsCSChComb) > 0:
                        axs[0].plot(payloadsCSChComb, valsCSChComb, color=combChCOL, linewidth=LW, marker="1", markersize=MS, linestyle=combChLS, label=combChHS + "(" + str(int(rate)) + ")"+" (crypto-sign)")
                if debugPlot:
                    if plotBasic:
                        for x,y,z in zip(payloadsCSBase, valsCSBase, numsCSBase):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCSCheap, valsCSCheap, numsCSCheap):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCSQuick, valsCSQuick, numsCSQuick):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCSDamq, valsCSDamq, numsCSDamq):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCCSomb, valsCSComb, numsCSComb):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCCSomb, valsCSDamr, numsCSDamr):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCCSomb, valsCSDama, numsCSDama):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCCSomb, valsCSDamp, numsCSDamp):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCSFree, valsCSFree, numsCSFree):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCSRoll, valsCSRoll, numsCSRoll):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCSOnep, valsCSOnep, numsCSOnep):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    if plotChained:
                        for x,y,z in zip(payloadsCSChBase, valsCSChBase, numsCSChBase):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCSChComb, valsCSChComb, numsCSChComb):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
            if plotCrypto: # Verif
                if plotBasic:
                    if len(payloadsCVBase) > 0:
                        axs[0].plot(payloadsCVBase,   valsCVBase,   color=baseCOL,   linewidth=LW, marker="2", markersize=MS, linestyle=baseLS,   label=baseHS + "(" + str(int(rate)) + ")"+" (crypto-verif)")
                    if len(payloadsCVCheap) > 0:
                        axs[0].plot(payloadsCVCheap,  valsCVCheap,  color=cheapCOL,  linewidth=LW, marker="2", markersize=MS, linestyle=cheapLS,  label=cheapHS + "(" + str(int(rate)) + ")"+" (crypto-verif)")
                    if len(payloadsCVQuick) > 0:
                        axs[0].plot(payloadsCVQuick,  valsCVQuick,  color=quickCOL,  linewidth=LW, marker="2", markersize=MS, linestyle=quickLS,  label=quickHS + "(" + str(int(rate)) + ")"+" (crypto-verif)")
                    if len(payloadsCVDamq) > 0:
                        axs[0].plot(payloadsCVDamq,   valsCVDamq,   color=damqCOL,   linewidth=LW, marker="2", markersize=MS, linestyle=damqLS,   label=damqHS + "(" + str(int(rate)) + ")"+" (crypto-verif)")
                    if len(payloadsCVComb) > 0:
                        axs[0].plot(payloadsCVComb,   valsCVComb,   color=combCOL,   linewidth=LW, marker="2", markersize=MS, linestyle=combLS,   label=combHS + "(" + str(int(rate)) + ")"+" (crypto-verif)")
                    if len(payloadsCVDamr) > 0:
                        axs[0].plot(payloadsCVDamr,   valsCVDamr,   color=damrCOL,   linewidth=LW, marker="2", markersize=MS, linestyle=damrLS,   label=damrHS + "(" + str(int(rate)) + ")"+" (crypto-verif)")
                    if len(payloadsCVDama) > 0:
                        axs[0].plot(payloadsCVDama,   valsCVDama,   color=damaCOL,   linewidth=LW, marker="2", markersize=MS, linestyle=damaLS,   label=damaHS + "(" + str(int(rate)) + ")"+" (crypto-verif)")
                    if len(payloadsCVDamp) > 0:
                        axs[0].plot(payloadsCVDamp,   valsCVDamp,   color=dampCOL,   linewidth=LW, marker="2", markersize=MS, linestyle=dampLS,   label=dampHS + "(" + str(int(rate)) + ")"+" (crypto-verif)")
                    if len(payloadsCVFree) > 0:
                        axs[0].plot(payloadsCVFree,   valsCVFree,   color=freeCOL,   linewidth=LW, marker="2", markersize=MS, linestyle=freeLS,   label=freeHS + "(" + str(int(rate)) + ")"+" (crypto-verif)")
                    if len(payloadsCVRoll) > 0:
                        axs[0].plot(payloadsCVRoll,   valsCVRoll,   color=rollCOL,   linewidth=LW, marker="2", markersize=MS, linestyle=rollLS,   label=rollHS + "(" + str(int(rate)) + ")"+" (crypto-verif)")
                    if len(payloadsCVOnep) > 0:
                        axs[0].plot(payloadsCVOnep,   valsCVOnep,   color=onepCOL,   linewidth=LW, marker="2", markersize=MS, linestyle=onepLS,   label=onepHS + "(" + str(int(rate)) + ")"+" (crypto-verif)")
                if plotChained:
                    if len(payloadsCVChBase) > 0:
                        axs[0].plot(payloadsCVChBase, valsCVChBase, color=baseChCOL, linewidth=LW, marker="2", markersize=MS, linestyle=baseChLS, label=baseChHS + "(" + str(int(rate)) + ")"+" (crypto-verif)")
                    if len(payloadsCVChComb) > 0:
                        axs[0].plot(payloadsCVChComb, valsCVChComb, color=combChCOL, linewidth=LW, marker="2", markersize=MS, linestyle=combChLS, label=combChHS + "(" + str(int(rate)) + ")"+" (crypto-verif)")
                if debugPlot:
                    if plotBasic:
                        for x,y,z in zip(payloadsCVBase, valsCVBase, numsCVBase):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCVCheap, valsCVCheap, numsCVCheap):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCVQuick, valsCVQuick, numsCVQuick):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCVDamq, valsCVDamq, numsCVDamq):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCCVomb, valsCVComb, numsCVComb):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCCVomb, valsCVDamr, numsCVDamr):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCCVomb, valsCVDama, numsCVDama):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCCVomb, valsCVDamp, numsCVDamp):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCVFree, valsCVFree, numsCVFree):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCVRoll, valsCVRoll, numsCVRoll):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCVOnep, valsCVOnep, numsCVOnep):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                    if plotChained:
                        for x,y,z in zip(payloadsCVChBase, valsCVChBase, numsCVChBase):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
                        for x,y,z in zip(payloadsCVChComb, valsCVChComb, numsCVChComb):
                            axs[0].annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
        # legend
        if showLegend2 or (showLegend1 and not plotThroughput):
            ax.legend(prop={'size': 9})

    #fig.subplots_adjust(hspace=0.5)
    fig.savefig(plotFile, bbox_inches='tight', pad_inches=0.05)
    print("view-times are in", timesFile)
    print("points are in", files)
    print("plot is in", plotFile)
    if displayPlot:
        try:
            subprocess.call([displayApp, plotFile])
        except:
            print("couldn't display the plot using '" + displayApp + "'. Consider changing the 'displayApp' variable.")
# End of createPlotPayload


## Run experiments so that all protocols use the same number of nodes, and we vary the number of faults
## numFaults is used as the basis to compute the actual number of faults: 2* or 3* depending on the protocol
def runExperimentsFaults(numFaults):
    # Creating stats directory
    Path(statsdir).mkdir(parents=True, exist_ok=True)

    printNodePointParams()

    l = range(2*numFaults+1)
    print("will test the following numbers of dead nodes: ", l)

    for numDeadNodes in l: # i.e., from 0 to numFaults
        # ------
        # HotStuff-like baseline
        if runBase:
            computeAvgStats(recompile,protocol=Protocol.BASE,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=2*numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Cheap-HotStuff (TEE locked/prepared blocks)
        if runCheap:
            computeAvgStats(recompile,protocol=Protocol.CHEAP,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=3*numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Quick-HotStuff (Accumulator)
        if runQuick:
            computeAvgStats(recompile,protocol=Protocol.QUICK,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=2*numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Damysus-A (Accumulator) + Pacemaker
        if runDamq:
            computeAvgStats(recompile,protocol=Protocol.DAMQ,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=2*numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Quick-HotStuff (Accumulator) - debug version
        if runQuickDbg:
            computeAvgStats(recompile,protocol=Protocol.QUICKDBG,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=2*numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Combines Cheap&Quick-HotStuff
        if runComb:
            computeAvgStats(recompile,protocol=Protocol.COMB,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=3*numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Damysus + kinda ROTE
        if runDamr:
            computeAvgStats(recompile,protocol=Protocol.DAMR,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=3*numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Damysus + kinda Achilles
        if runDama:
            computeAvgStats(recompile,protocol=Protocol.DAMA,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=3*numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Damysus + Pacemaker
        if runDamp:
            computeAvgStats(recompile,protocol=Protocol.DAMP,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=3*numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Free
        if runFree:
            computeAvgStats(recompile,protocol=Protocol.FREE,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=3*numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Roll
        if runRoll:
            computeAvgStats(recompile,protocol=Protocol.ROLL,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=3*numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Onep
        if runOnep:
            computeAvgStats(recompile,protocol=Protocol.ONEP,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=3*numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # OnepB
        if runOnepB:
            computeAvgStats(recompile,protocol=Protocol.ONEPB,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=3*numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # OnepC
        if runOnepC:
            computeAvgStats(recompile,protocol=Protocol.ONEPC,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=3*numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # OnepD
        if runOnepD:
            computeAvgStats(recompile,protocol=Protocol.ONEPD,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=3*numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Chained HotStuff-like baseline
        if runChBase:
            computeAvgStats(recompile,protocol=Protocol.CHBASE,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=2*numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Chained Cheap&Quick
        if runChComb:
            computeAvgStats(recompile,protocol=Protocol.CHCOMB,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=3*numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Chained Cheap&Quick - debug version
        if runChCombDbg:
            computeAvgStats(recompile,protocol=Protocol.CHCOMBDBG,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=3*numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)

    print("num complete runs=", completeRuns)
    print("num aborted runs=", abortedRuns)
    print("aborted runs:", aborted)

    createPlot(pointsFile)
# End of runExperiments


def runExperiments():
    # Creating stats directory
    Path(statsdir).mkdir(parents=True, exist_ok=True)

    printNodePointParams()

    g = open(timesFile, 'a')
    g.write("## lat="+str(networkLat)+" rate="+str(rateMbit)+" payload="+str(payloadSize)+"\n")
    g.close()

    for numFaults in faults:
        numDeadNodes = numDeadNodesCfg

        # ------
        # HotStuff-like baseline
        if runBase:
            computeAvgStats(recompile,protocol=Protocol.BASE,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Cheap-HotStuff (TEE locked/prepared blocks)
        if runCheap:
            computeAvgStats(recompile,protocol=Protocol.CHEAP,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Quick-HotStuff (Accumulator)
        if runQuick:
            computeAvgStats(recompile,protocol=Protocol.QUICK,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Damysus-A (Accumulator) + Pacemaker
        if runDamq:
            computeAvgStats(recompile,protocol=Protocol.DAMQ,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Quick-HotStuff (Accumulator) - debug version
        if runQuickDbg:
            computeAvgStats(recompile,protocol=Protocol.QUICKDBG,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Combines Cheap&Quick-HotStuff
        if runComb:
            computeAvgStats(recompile,protocol=Protocol.COMB,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Damysus + kinda ROTE
        if runDamr:
            computeAvgStats(recompile,protocol=Protocol.DAMR,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Damysus + kinda Achilles
        if runDama:
            computeAvgStats(recompile,protocol=Protocol.DAMA,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Damysus + Pacemaker
        if runDamp:
            computeAvgStats(recompile,protocol=Protocol.DAMP,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Free
        if runFree:
            computeAvgStats(recompile,protocol=Protocol.FREE,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Roll
        if runRoll:
            computeAvgStats(recompile,protocol=Protocol.ROLL,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Onep
        if runOnep:
            computeAvgStats(recompile,protocol=Protocol.ONEP,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # OnepB
        if runOnepB:
            computeAvgStats(recompile,protocol=Protocol.ONEPB,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # OnepC
        if runOnepC:
            computeAvgStats(recompile,protocol=Protocol.ONEPC,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # OnepD
        if runOnepD:
            computeAvgStats(recompile,protocol=Protocol.ONEPD,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Chained HotStuff-like baseline
        if runChBase:
            computeAvgStats(recompile,protocol=Protocol.CHBASE,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Chained Cheap&Quick
        if runChComb:
            computeAvgStats(recompile,protocol=Protocol.CHCOMB,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Chained Cheap&Quick - debug version
        if runChCombDbg:
            computeAvgStats(recompile,protocol=Protocol.CHCOMBDBG,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=numJoiners,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)

    print("num complete runs=", completeRuns)
    print("num aborted runs=", abortedRuns)
    print("aborted runs:", aborted)

    createPlot(pointsFile)
# End of runExperiments


## For p9 - to run experiments where we vary the number of nodes trying to rejoin the system
def runExperimentsJoin(numFaults,joiners):
    # Creating stats directory
    Path(statsdir).mkdir(parents=True, exist_ok=True)

    printNodePointParams()

    print("will test the following number of joiners: ", joiners)

    numDeadNodes = numDeadNodesCfg

    for j in joiners:
        print("number of joiners: ", j)

        # ------
        # HotStuff-like baseline
        if runBase:
            computeAvgStats(recompile,protocol=Protocol.BASE,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Cheap-HotStuff (TEE locked/prepared blocks)
        if runCheap:
            computeAvgStats(recompile,protocol=Protocol.CHEAP,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Quick-HotStuff (Accumulator)
        if runQuick:
            computeAvgStats(recompile,protocol=Protocol.QUICK,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Damysus-A (Accumulator) + Pacemaker
        if runDamq:
            computeAvgStats(recompile,protocol=Protocol.DAMQ,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Quick-HotStuff (Accumulator) - debug version
        if runQuickDbg:
            computeAvgStats(recompile,protocol=Protocol.QUICKDBG,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Combines Cheap&Quick-HotStuff
        if runComb:
            computeAvgStats(recompile,protocol=Protocol.COMB,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Damysus + kinda ROTE
        if runDamr:
            computeAvgStats(recompile,protocol=Protocol.DAMR,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Damysus + kinda Achilles
        if runDama:
            computeAvgStats(recompile,protocol=Protocol.DAMA,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Damysus + Pacemaker
        if runDamp:
            computeAvgStats(recompile,protocol=Protocol.DAMP,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Free
        if runFree:
            computeAvgStats(recompile,protocol=Protocol.FREE,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Roll
        if runRoll:
            computeAvgStats(recompile,protocol=Protocol.ROLL,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Onep
        if runOnep:
            computeAvgStats(recompile,protocol=Protocol.ONEP,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # OnepB
        if runOnepB:
            computeAvgStats(recompile,protocol=Protocol.ONEPB,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # OnepC
        if runOnepC:
            computeAvgStats(recompile,protocol=Protocol.ONEPC,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # OnepD
        if runOnepD:
            computeAvgStats(recompile,protocol=Protocol.ONEPD,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Chained HotStuff-like baseline
        if runChBase:
            computeAvgStats(recompile,protocol=Protocol.CHBASE,constFactor=3,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Chained Cheap&Quick
        if runChComb:
            computeAvgStats(recompile,protocol=Protocol.CHCOMB,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)
        # ------
        # Chained Cheap&Quick - debug version
        if runChCombDbg:
            computeAvgStats(recompile,protocol=Protocol.CHCOMBDBG,constFactor=2,numClTrans=numClTrans,sleepTime=sleepTime,numViews=numViews,cutOffBound=cutOffBound,numFaults=numFaults,numJoiners=j,numDeadNodes=numDeadNodes,numRepeats=repeats)
        else:
            (0.0,0.0,0.0,0.0)

    print("num complete runs=", completeRuns)
    print("num aborted runs=", abortedRuns)
    print("aborted runs:", aborted)

    createPlotJoin(pointsFile)
# End of runExperimentsJoin


def printClientPoint(protocol,sleepTime,numFaults,throughput,latency,numPoints):
    f = open(clientsFile, 'a')
    f.write("protocol="+protocol.value+" "+"sleep="+str(sleepTime)+" "+"faults="+str(numFaults)+" throughput="+str(throughput)+" latency="+str(latency)+" numPoints="+str(numPoints)+"\n")
    f.close()
# End of printClientPoint


def computeClientStats(protocol,numClTrans,sleepTime,numFaults):
    throughputs = []
    latencies   = []
    files       = glob.glob(statsdir+"/*")
    for filename in files:
        if filename.startswith(statsdir+"/client-throughput-latency"):
            f = open(filename, "r")
            s = f.read()
            [thr,lat] = s.split(" ")
            throughputs.append(float(thr))
            latencies.append(float(lat))

    # we remove the top and bottom 10% quantiles
    l   = len(latencies)
    num = int(l/(100/quantileSize))

    throughputs = sorted(throughputs)
    latencies   = sorted(latencies)

    newthroughputs = throughputs[num:l-num]
    newlatencies   = latencies[num:l-num]

    throughput = 0.0
    for i in newthroughputs:
        throughput += i
    throughput = throughput/len(newthroughputs) if len(newthroughputs) > 0 else -1.0

    latency = 0.0
    for i in newlatencies:
        latency += i
    latency = latency/len(newlatencies) if len(newlatencies) > 0 else -1.0

    f = open(debugFile, 'a')
    f.write("------------------------------\n")
    f.write("numClTrans="+str(numClTrans)+";sleepTime="+str(sleepTime)+";length="+str(l)+";remove="+str(num)+";throughput="+str(throughput)+";latency="+str(latency)+"\n")
    f.write("before:\n")
    f.write(str(throughputs)+"\n")
    f.write(str(latencies)+"\n")
    f.write("after:\n")
    f.write(str(newthroughputs)+"\n")
    f.write(str(newlatencies)+"\n")
    f.close()
    print("numClTrans="+str(numClTrans)+";sleepTime="+str(sleepTime)+";length="+str(l)+";remove="+str(num)+";throughput="+str(throughput)+";latency="+str(latency))
    print("before:")
    print(throughputs)
    print(latencies)
    print("after:")
    print(newthroughputs)
    print(newlatencies)

    numPoints = l-(2*num)
    printClientPoint(protocol,sleepTime,numFaults,throughput,latency,numPoints)
# Enf of computeClientStats


def createTVLplot(cFile,instances):
    LBase = []
    TBase = []
    aBase = []

    LCheap = []
    TCheap = []
    aCheap = []

    LQuick = []
    TQuick = []
    aQuick = []

    LDamq = []
    TDamq = []
    aDamq = []

    LComb = []
    TComb = []
    aComb = []

    LDamr = []
    TDamr = []
    aDamr = []

    LDama = []
    TDama = []
    aDama = []

    LDamp = []
    TDamp = []
    aDamp = []

    LFree = []
    TFree = []
    aFree = []

    LRoll = []
    TRoll = []
    aRoll = []

    LOnep = []
    TOnep = []
    aOnep = []

    LOnepB = []
    TOnepB = []
    aOnepB = []

    LOnepC = []
    TOnepC = []
    aOnepC = []

    LOnepD = []
    TOnepD = []
    aOnepD = []

    LChBase = []
    TChBase = []
    aChBase = []

    LChComb = []
    TChComb = []
    aChComb = []

    print("reading points from:", cFile)
    f = open(cFile,'r')
    for line in f.readlines():
        if line.startswith("protocol"):
            [prot,slp,faults,thr,lat,np] = line.split(" ")
            [protTag,protVal]     = prot.split("=")
            [sleepTag,sleepVal]   = slp.split("=")
            [faultsTag,faultsVal] = faults.split("=")
            [thrTag,thrVal]       = thr.split("=")
            [latTag,latVal]       = lat.split("=")
            [npTag,npVal]         = np.split("=") # number of points
            throughput = float(thrVal)
            latency    = float(latVal)
            sleep      = float(sleepVal)
            if protVal == "BASIC_BASELINE":
                TBase.append(throughput)
                LBase.append(latency)
                aBase.append(sleep)
            if protVal == "BASIC_CHEAP":
                TCheap.append(throughput)
                LCheap.append(latency)
                aCheap.append(sleep)
            if protVal == "BASIC_QUICK":
                TQuick.append(throughput)
                LQuick.append(latency)
                aQuick.append(sleep)
            if protVal == "BASIC_QUICK_DEBUG":
                TQuick.append(throughput)
                LQuick.append(latency)
                aQuick.append(sleep)
            if protVal == "BASIC_CHEAP_AND_QUICK":
                TComb.append(throughput)
                LComb.append(latency)
                aComb.append(sleep)
            if protVal == "BASIC_DAMYSUS_ROTE":
                TDamr.append(throughput)
                LDamr.append(latency)
                aDamr.append(sleep)
            if protVal == "BASIC_DAMYSUS_ACHILLES":
                TDama.append(throughput)
                LDama.append(latency)
                aDama.append(sleep)
            if protVal == "BASIC_DAMYSUS_PACEMAKER":
                TDamp.append(throughput)
                LDamp.append(latency)
                aDamp.append(sleep)
            if protVal == "BASIC_DAMYSUS3_PACEMAKER":
                TDamq.append(throughput)
                LDamq.append(latency)
                aDamq.append(sleep)
            if protVal == "BASIC_FREE":
                TFree.append(throughput)
                LFree.append(latency)
                aFree.append(sleep)
            if protVal == "BASIC_ROLL":
                TRoll.append(throughput)
                LRoll.append(latency)
                aRoll.append(sleep)
            if protVal == "BASIC_ONEP":
                TOnep.append(throughput)
                LOnep.append(latency)
                aOnep.append(sleep)
            if protVal == "BASIC_ONEPB":
                TOnepB.append(throughput)
                LOnepB.append(latency)
                aOnepB.append(sleep)
            if protVal == "BASIC_ONEPC":
                TOnepC.append(throughput)
                LOnepC.append(latency)
                aOnepC.append(sleep)
            if protVal == "BASIC_ONEPD":
                TOnepD.append(throughput)
                LOnepD.append(latency)
                aOnepD.append(sleep)
            if protVal == "CHAINED_BASELINE":
                TChBase.append(throughput)
                LChBase.append(latency)
                aChBase.append(sleep)
            if protVal == "CHAINED_CHEAP_AND_QUICK":
                TChComb.append(throughput)
                LChComb.append(latency)
                aChComb.append(sleep)
            if protVal == "CHAINED_CHEAP_AND_QUICK_DEBUG":
                TChComb.append(throughput)
                LChComb.append(latency)
                aChComb.append(sleep)

    LW = 1 # linewidth
    MS = 5 # markersize
    XYT = (0,5)

    #fig, ax=plt.subplots()

    plt.cla()
    plt.clf()

    ## Plotting
    print("plotting")
    if debugPlot:
        plt.title("Throughput vs. Latency\n(file="+cFile+",instances="+str(instances)+")")
    # else:
    #     plt.title("Throughput vs. Latency")

    plt.xlabel("throughput (Kops/sec)", fontsize=12)
    plt.ylabel("latency (ms)", fontsize=12)
    if plotBasic:
        if len(TBase) > 0:
            plt.plot(TBase,   LBase,   color=baseCOL,   linewidth=LW, marker=baseMRK,   markersize=MS, linestyle=baseLS,   label=baseHS)
        if len(TCheap) > 0:
            plt.plot(TCheap,  LCheap,  color=cheapCOL,  linewidth=LW, marker=cheapMRK,  markersize=MS, linestyle=cheapLS,  label=cheapHS)
        if len(TQuick) > 0:
            plt.plot(TQuick,  LQuick,  color=quickCOL,  linewidth=LW, marker=quickMRK,  markersize=MS, linestyle=quickLS,  label=quickHS)
        if len(TDamq) > 0:
            plt.plot(TDamq,   LDamq,   color=damqCOL,   linewidth=LW, marker=damqMRK,   markersize=MS, linestyle=damqLS,   label=damqHS)
        if len(TComb) > 0:
            plt.plot(TComb,   LComb,   color=combCOL,   linewidth=LW, marker=combMRK,   markersize=MS, linestyle=combLS,   label=combHS)
        if len(TDamr) > 0:
            plt.plot(TDamr,   LDamr,   color=damrCOL,   linewidth=LW, marker=damrMRK,   markersize=MS, linestyle=damrLS,   label=damrHS)
        if len(TDama) > 0:
            plt.plot(TDama,   LDama,   color=damaCOL,   linewidth=LW, marker=damaMRK,   markersize=MS, linestyle=damaLS,   label=damaHS)
        if len(TDamp) > 0:
            plt.plot(TDamp,   LDamp,   color=dampCOL,   linewidth=LW, marker=dampMRK,   markersize=MS, linestyle=dampLS,   label=dampHS)
        if len(TFree) > 0:
            plt.plot(TFree,   LFree,   color=freeCOL,   linewidth=LW, marker=freeMRK,   markersize=MS, linestyle=freeLS,   label=freeHS)
        if len(TRoll) > 0:
            plt.plot(TRoll,   LRoll,   color=rollCOL,   linewidth=LW, marker=rollMRK,   markersize=MS, linestyle=rollLS,   label=rollHS)
        if len(TOnep) > 0:
            plt.plot(TOnep,   LOnep,   color=onepCOL,   linewidth=LW, marker=onepMRK,   markersize=MS, linestyle=onepLS,   label=onepHS)
        if len(TOnepB) > 0:
            plt.plot(TOnepB,  LOnepB,  color=onepbCOL,  linewidth=LW, marker=onepbMRK,  markersize=MS, linestyle=onepbLS,  label=onepbHS)
        if len(TOnepC) > 0:
            plt.plot(TOnepC,  LOnepC,  color=onepcCOL,  linewidth=LW, marker=onepcMRK,  markersize=MS, linestyle=onepcLS,  label=onepcHS)
        if len(TOnepD) > 0:
            plt.plot(TOnepD,  LOnepD,  color=onepdCOL,  linewidth=LW, marker=onepdMRK,  markersize=MS, linestyle=onepdLS,  label=onepdHS)
    if plotChained:
        if len(TChBase) > 0:
            plt.plot(TChBase, LChBase, color=baseChCOL, linewidth=LW, marker=baseChMRK, markersize=MS, linestyle=baseChLS, label=baseChHS)
        if len(TChComb) > 0:
            plt.plot(TChComb, LChComb, color=combChCOL, linewidth=LW, marker=combChMRK, markersize=MS, linestyle=combChLS, label=combChHS)
    if debugPlot:
        if plotBasic:
            for x,y,z in zip(TBase, LBase, aBase):
                plt.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
            for x,y,z in zip(TCheap, LCheap, aCheap):
                plt.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
            for x,y,z in zip(TQuick, LQuick, aQuick):
                plt.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
            for x,y,z in zip(TDamq, LDamq, aDamq):
                plt.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
            for x,y,z in zip(TComb, LComb, aComb):
                plt.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
            for x,y,z in zip(TDamr, LDamr, aDamr):
                plt.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
            for x,y,z in zip(TDama, LDama, aDama):
                plt.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
            for x,y,z in zip(TDamp, LDamp, aDamp):
                plt.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
            for x,y,z in zip(TFree, LFree, aFree):
                plt.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
            for x,y,z in zip(TRoll, LRoll, aRoll):
                plt.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
            for x,y,z in zip(TOnep, LOnep, aOnep):
                plt.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
            for x,y,z in zip(TOnepB, LOnepB, aOnepB):
                plt.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
            for x,y,z in zip(TOnepC, LOnepC, aOnepC):
                plt.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
            for x,y,z in zip(TOnepD, LOnepD, aOnepD):
                plt.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
        if plotChained:
            for x,y,z in zip(TChBase, LChBase, aChBase):
                plt.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')
            for x,y,z in zip(TChComb, LChComb, aChComb):
                plt.annotate(z,(x,y),textcoords="offset points",xytext=XYT,ha='center')

    # Font
    plt.rcParams.update({'font.size': 12})

    # legend
    plt.legend()

    #ax.set_aspect(aspect=0.1)
    if logScale:
        plt.yscale('log')
    #plt.yscale('log',base=2)

    #plt.minorticks_on()
    #plt.grid(axis = 'y')
    plt.savefig(tvlFile, bbox_inches='tight', pad_inches=0.05)
    print("plot is in", tvlFile)
    if displayPlot:
        subprocess.call([displayApp,tvlFile])
# Enf of createTVLplot


def oneTVL(protocol,constFactor,numFaults,numTransPerBlock,payloadSize,numClTrans,numViews,cutOffBound,sleepTimes,repeats):
    numReps = (constFactor * numFaults) + 1

    if runDocker:
        startContainers(numReps,numClients)

    mkApp(protocol,constFactor,numFaults,numTransPerBlock,payloadSize)
    for sleepTime in sleepTimes:
        clearStatsDir()
        for i in range(repeats):
            print(">>>>>>>>>>>>>>>>>>>>",
                  "protocol="+protocol.value,
                  ";regions="+regions[0],
                  ";payload="+str(payloadSize),
                  ";factor="+str(constFactor),
                  ";sleep="+str(sleepTime),
                  ";#faults="+str(numFaults),
                  ";repeat="+str(i))
            time.sleep(2)
            execute(protocol,constFactor,numClTrans,sleepTime,numViews,cutOffBound,numFaults,numDeadNodes,numJoiners,i)
        computeClientStats(protocol,numClTrans,sleepTime,numFaults)

    if runDocker:
        stopContainers(numReps,numClients)
# End of oneTVL


# throuput vs. latency
def TVL():
    # Creating stats directory
    Path(statsdir).mkdir(parents=True, exist_ok=True)

    global expmode
    expmode = "TVL"

    global debugPlot
    debugPlot = True

    # Values for the non-chained versions
    #numClTrans   = 110000
    numClTrans   = 100000 #250000 #260000 #500000 # - 100000 seems fine for basic versions
    #numClients   = 5 #2 #16 #1 # --- 1 seems fine for basic versions

    # Values for the chained version
    numClTransCh = 100000 #250000 #260000 #500000 # - 100000 seems fine for basic versions
    #numClientsCh = 6 #4 #16 #1 # --- 1 seems fine for basic versions

    numFaults        = 1
    numTransPerBlock = 400 #10
    payloadSize      = 0 #256
    numViews         = 0 # nodes don't stop
    cutOffBound      = 240


    ## For testing purposes, we use less repeats then
    test = True


    if test:
        sleepTimes = [500,100,50,10,5,0]
        #sleepTimes = [900,500,50,10]
    else:
        sleepTimes = [900,700,500,100,50,10,5,0] #[500,50,0] #

    f = open(clientsFile, 'a')
    f.write("# transactions="+str(numClTrans)+" "+
            "faults="+str(numFaults)+" "+
            "transactions="+str(numTransPerBlock)+" "+
            "payload="+str(payloadSize)+" "+
            "cutoff="+str(cutOffBound)+" "+
            "repeats="+str(repeats)+" "+
            "rates="+str(sleepTimes)+"\n")
    f.close()

    ## TODO : make this a parameter instead
    global numClients
    numClients = numNonChCls

    # HotStuff-like baseline
    if runBase:
        oneTVL(protocol=Protocol.BASE,
               constFactor=3,
               numFaults=numFaults,
               numTransPerBlock=numTransPerBlock,
               payloadSize=payloadSize,
               numClTrans=numClTrans,
               numViews=numViews,
               cutOffBound=cutOffBound,
               sleepTimes=sleepTimes,
               repeats=repeats)

    # Cheap-HotStuff
    if runCheap:
        oneTVL(protocol=Protocol.CHEAP,
               constFactor=2,
               numFaults=numFaults,
               numTransPerBlock=numTransPerBlock,
               payloadSize=payloadSize,
               numClTrans=numClTrans,
               numViews=numViews,
               cutOffBound=cutOffBound,
               sleepTimes=sleepTimes,
               repeats=repeats)

    # Quick-HotStuff
    if runQuick:
        oneTVL(protocol=Protocol.QUICK,
               constFactor=3,
               numFaults=numFaults,
               numTransPerBlock=numTransPerBlock,
               payloadSize=payloadSize,
               numClTrans=numClTrans,
               numViews=numViews,
               cutOffBound=cutOffBound,
               sleepTimes=sleepTimes,
               repeats=repeats)

    # Damysus + Pacemaker + 3f+1 nodes
    if runDamq:
        oneTVL(protocol=Protocol.DAMQ,
               constFactor=3,
               numFaults=numFaults,
               numTransPerBlock=numTransPerBlock,
               payloadSize=payloadSize,
               numClTrans=numClTrans,
               numViews=numViews,
               cutOffBound=cutOffBound,
               sleepTimes=sleepTimes,
               repeats=repeats)

    # Quick-HotStuff - debug version
    if runQuickDbg:
        oneTVL(protocol=Protocol.QUICKDBG,
               constFactor=3,
               numFaults=numFaults,
               numTransPerBlock=numTransPerBlock,
               payloadSize=payloadSize,
               numClTrans=numClTrans,
               numViews=numViews,
               cutOffBound=cutOffBound,
               sleepTimes=sleepTimes,
               repeats=repeats)

    # Cheap&Quick-HotStuff
    if runComb:
        oneTVL(protocol=Protocol.COMB,
               constFactor=2,
               numFaults=numFaults,
               numTransPerBlock=numTransPerBlock,
               payloadSize=payloadSize,
               numClTrans=numClTrans,
               numViews=numViews,
               cutOffBound=cutOffBound,
               sleepTimes=sleepTimes,
               repeats=repeats)

    # Damysus + kinda ROTE
    if runDamr:
        oneTVL(protocol=Protocol.DAMR,
               constFactor=2,
               numFaults=numFaults,
               numTransPerBlock=numTransPerBlock,
               payloadSize=payloadSize,
               numClTrans=numClTrans,
               numViews=numViews,
               cutOffBound=cutOffBound,
               sleepTimes=sleepTimes,
               repeats=repeats)

    # Damysus + kinda Achilles
    if runDama:
        oneTVL(protocol=Protocol.DAMA,
               constFactor=2,
               numFaults=numFaults,
               numTransPerBlock=numTransPerBlock,
               payloadSize=payloadSize,
               numClTrans=numClTrans,
               numViews=numViews,
               cutOffBound=cutOffBound,
               sleepTimes=sleepTimes,
               repeats=repeats)

    # Damysus + Pacemaker
    if runDamp:
        oneTVL(protocol=Protocol.DAMP,
               constFactor=2,
               numFaults=numFaults,
               numTransPerBlock=numTransPerBlock,
               payloadSize=payloadSize,
               numClTrans=numClTrans,
               numViews=numViews,
               cutOffBound=cutOffBound,
               sleepTimes=sleepTimes,
               repeats=repeats)

    # Free
    if runFree:
        oneTVL(protocol=Protocol.FREE,
               constFactor=2,
               numFaults=numFaults,
               numTransPerBlock=numTransPerBlock,
               payloadSize=payloadSize,
               numClTrans=numClTrans,
               numViews=numViews,
               cutOffBound=cutOffBound,
               sleepTimes=sleepTimes,
               repeats=repeats)

    # Roll
    if runRoll:
        oneTVL(protocol=Protocol.ROLL,
               constFactor=2,
               numFaults=numFaults,
               numTransPerBlock=numTransPerBlock,
               payloadSize=payloadSize,
               numClTrans=numClTrans,
               numViews=numViews,
               cutOffBound=cutOffBound,
               sleepTimes=sleepTimes,
               repeats=repeats)

    # Onep
    if runOnep:
        oneTVL(protocol=Protocol.ONEP,
               constFactor=2,
               numFaults=numFaults,
               numTransPerBlock=numTransPerBlock,
               payloadSize=payloadSize,
               numClTrans=numClTrans,
               numViews=numViews,
               cutOffBound=cutOffBound,
               sleepTimes=sleepTimes,
               repeats=repeats)

    # OnepB
    if runOnepB:
        oneTVL(protocol=Protocol.ONEPB,
               constFactor=2,
               numFaults=numFaults,
               numTransPerBlock=numTransPerBlock,
               payloadSize=payloadSize,
               numClTrans=numClTrans,
               numViews=numViews,
               cutOffBound=cutOffBound,
               sleepTimes=sleepTimes,
               repeats=repeats)

    # OnepC
    if runOnepC:
        oneTVL(protocol=Protocol.ONEPC,
               constFactor=2,
               numFaults=numFaults,
               numTransPerBlock=numTransPerBlock,
               payloadSize=payloadSize,
               numClTrans=numClTrans,
               numViews=numViews,
               cutOffBound=cutOffBound,
               sleepTimes=sleepTimes,
               repeats=repeats)

    # OnepD
    if runOnepD:
        oneTVL(protocol=Protocol.ONEPD,
               constFactor=2,
               numFaults=numFaults,
               numTransPerBlock=numTransPerBlock,
               payloadSize=payloadSize,
               numClTrans=numClTrans,
               numViews=numViews,
               cutOffBound=cutOffBound,
               sleepTimes=sleepTimes,
               repeats=repeats)

    numClients = numChCls

    # Chained HotStuff-like baseline
    if runChBase:
        oneTVL(protocol=Protocol.CHBASE,
               constFactor=3,
               numFaults=numFaults,
               numTransPerBlock=numTransPerBlock,
               payloadSize=payloadSize,
               numClTrans=numClTransCh,
               numViews=numViews,
               cutOffBound=cutOffBound,
               sleepTimes=sleepTimes,
               repeats=repeats)

    # Chained Cheap&Quick-HotStuff
    if runChComb:
        oneTVL(protocol=Protocol.CHCOMB,
               constFactor=2,
               numFaults=numFaults,
               numTransPerBlock=numTransPerBlock,
               payloadSize=payloadSize,
               numClTrans=numClTransCh,
               numViews=numViews,
               cutOffBound=cutOffBound,
               sleepTimes=sleepTimes,
               repeats=repeats)

    # Chained Cheap&Quick-HotStuff - debug version
    if runChCombDbg:
        oneTVL(protocol=Protocol.CHCOMBDBG,
               constFactor=2,
               numFaults=numFaults,
               numTransPerBlock=numTransPerBlock,
               payloadSize=payloadSize,
               numClTrans=numClTransCh,
               numViews=numViews,
               cutOffBound=cutOffBound,
               sleepTimes=sleepTimes,
               repeats=repeats)

    createTVLplot(clientsFile,numClTrans)
    print("debug info is in", debugFile)
# End of TVL


def oneTVLaws(protocol,constFactor,numFaults,allRepIds,allClIds,numTransPerBlock,payloadSize,numCl,numClTrans,numViews,cutOffBound,sleepTimes,repeats):
    global numClients
    numClients = numCl

    numReps = (constFactor * numFaults) + 1
    instanceRepIds = allRepIds[0:numReps]
    instanceClIds = allClIds

    mkParams(protocol,constFactor,numFaults,numTransPerBlock,payloadSize)
    #time.sleep(5)
    makeInstances(instanceRepIds+instanceClIds,protocol)

    # sleepTimes holds different rates at which clients send data
    for sleepTime in sleepTimes:
        clearStatsDir()
        for i in range(repeats):
            print(">>>>>>>>>>>>>>>>>>>>",
                  "protocol="+protocol.value,
                  ";regions="+regions[0],
                  ";payload="+str(payloadSize),
                  "(factor="+str(constFactor)+")",
                  "sleep="+str(sleepTime),
                  "#faults="+str(numFaults),
                  "repeat="+str(i))
            time.sleep(2)
            executeInstances(instanceRepIds,instanceClIds,protocol,constFactor,numClTrans,sleepTime,numViews,cutOffBound,numFaults,numJoiners,i)
        # copy the stats over
        copyClientStats(instanceClIds)
        computeClientStats(protocol,numClTrans,sleepTime,numFaults)
# End of oneTVLaws


def TVLaws():
    global numMakeCores
    numMakeCores = 1

    global expmode
    expmode = "TVL"

    global debugPlot
    debugPlot = True

    global regions
    regions = (EUregionsNAME, EUregions)

    global quantileSize
    quantileSize = 20

    ## 10 clients & 500000 was too much for Chained-HotStuff (30-Sept-2021-08 file)
    ## 10 clients & 200000 was not enough
    ## 10 clients & 250000 was not enough
    ## 10 clients & 280000 270000 a bit too much?
    ## 10 clients & 300000 seems to be fine (need to rerun) - maybe a bit too high?

    ## For testing purposes, we use less repeats then
    test = True

    # Values for the non-chained versions
    numClTrans   = 250000 #250000 #260000 #500000 # - 100000 seems fine for basic versions
    numClients   = 10 #16 #1 # --- 1 seems fine for basic versions

    # Values for the chained version
    numClTransCh = 50000 #250000 #260000 #500000 # - 100000 seems fine for basic versions
    numClientsCh = 6 #4 #16 #1 # --- 1 seems fine for basic versions

    # Common parameters
    numFaults        = 1
    numTransPerBlock = 400
    payloadSize      = 0 #256
    numViews         = 0 # nodes don't stop
    cutOffBound      = 90
    #sleepTimes  = [500,200,100,50,10,5,2,1,0]
    #sleepTimes  = [500,100,50,10,5,1,0]

    if test:
        repeats    = 2 #5 #10
        sleepTimes = [900,500,50,0] #[700,500,100,50,10,5,0] #
    else:
        repeats    = 100 #10 #20 #5 #200 #70 #50
        sleepTimes = [900,700,500,100,50,10,5,0] #[500,50,0] #

    f = open(clientsFile, 'a')
    f.write("# clientTransactions="+str(numClTrans)+" "+
            "faults="+str(numFaults)+" "+
            "transactions="+str(numTransPerBlock)+" "+
            "payload="+str(payloadSize)+" "+
            "numClients="+str(numClients)+" "+
            "cutoff="+str(cutOffBound)+" "+
            "repeats="+str(repeats)+" "+
            "rates="+str(sleepTimes)+"\n")
    f.close()


    ## Non-Chained Versions

    # the max number of replicas
    numReps = (3 * numFaults) + 1
    (allRepIds, allClIds) = startInstances(numReps,numClients)

    if runBase:
        oneTVLaws(protocol=Protocol.BASE,
                  constFactor=3,
                  numFaults=numFaults,
                  allRepIds=allRepIds,
                  allClIds=allClIds,
                  numTransPerBlock=numTransPerBlock,
                  payloadSize=payloadSize,
                  numCl=numClients,
                  numClTrans=numClTrans,
                  numViews=numViews,
                  cutOffBound=cutOffBound,
                  sleepTimes=sleepTimes,
                  repeats=repeats)

    if runCheap:
        oneTVLaws(protocol=Protocol.CHEAP,
                  constFactor=2,
                  numFaults=numFaults,
                  allRepIds=allRepIds,
                  allClIds=allClIds,
                  numTransPerBlock=numTransPerBlock,
                  payloadSize=payloadSize,
                  numCl=numClients,
                  numClTrans=numClTrans,
                  numViews=numViews,
                  cutOffBound=cutOffBound,
                  sleepTimes=sleepTimes,
                  repeats=repeats)

    if runQuick:
        oneTVLaws(protocol=Protocol.QUICK,
                  constFactor=3,
                  numFaults=numFaults,
                  allRepIds=allRepIds,
                  allClIds=allClIds,
                  numTransPerBlock=numTransPerBlock,
                  payloadSize=payloadSize,
                  numCl=numClients,
                  numClTrans=numClTrans,
                  numViews=numViews,
                  cutOffBound=cutOffBound,
                  sleepTimes=sleepTimes,
                  repeats=repeats)

    if runDamq:
        oneTVLaws(protocol=Protocol.DAMQ,
                  constFactor=3,
                  numFaults=numFaults,
                  allRepIds=allRepIds,
                  allClIds=allClIds,
                  numTransPerBlock=numTransPerBlock,
                  payloadSize=payloadSize,
                  numCl=numClients,
                  numClTrans=numClTrans,
                  numViews=numViews,
                  cutOffBound=cutOffBound,
                  sleepTimes=sleepTimes,
                  repeats=repeats)

    if runComb:
        oneTVLaws(protocol=Protocol.COMB,
                  constFactor=2,
                  numFaults=numFaults,
                  allRepIds=allRepIds,
                  allClIds=allClIds,
                  numTransPerBlock=numTransPerBlock,
                  payloadSize=payloadSize,
                  numCl=numClients,
                  numClTrans=numClTrans,
                  numViews=numViews,
                  cutOffBound=cutOffBound,
                  sleepTimes=sleepTimes,
                  repeats=repeats)

    if runDamr:
        oneTVLaws(protocol=Protocol.DAMR,
                  constFactor=2,
                  numFaults=numFaults,
                  allRepIds=allRepIds,
                  allClIds=allClIds,
                  numTransPerBlock=numTransPerBlock,
                  payloadSize=payloadSize,
                  numCl=numClients,
                  numClTrans=numClTrans,
                  numViews=numViews,
                  cutOffBound=cutOffBound,
                  sleepTimes=sleepTimes,
                  repeats=repeats)

    if runDama:
        oneTVLaws(protocol=Protocol.DAMA,
                  constFactor=2,
                  numFaults=numFaults,
                  allRepIds=allRepIds,
                  allClIds=allClIds,
                  numTransPerBlock=numTransPerBlock,
                  payloadSize=payloadSize,
                  numCl=numClients,
                  numClTrans=numClTrans,
                  numViews=numViews,
                  cutOffBound=cutOffBound,
                  sleepTimes=sleepTimes,
                  repeats=repeats)

    if runDamp:
        oneTVLaws(protocol=Protocol.DAMP,
                  constFactor=2,
                  numFaults=numFaults,
                  allRepIds=allRepIds,
                  allClIds=allClIds,
                  numTransPerBlock=numTransPerBlock,
                  payloadSize=payloadSize,
                  numCl=numClients,
                  numClTrans=numClTrans,
                  numViews=numViews,
                  cutOffBound=cutOffBound,
                  sleepTimes=sleepTimes,
                  repeats=repeats)

    if runFree:
        oneTVLaws(protocol=Protocol.FREE,
                  constFactor=2,
                  numFaults=numFaults,
                  allRepIds=allRepIds,
                  allClIds=allClIds,
                  numTransPerBlock=numTransPerBlock,
                  payloadSize=payloadSize,
                  numCl=numClients,
                  numClTrans=numClTrans,
                  numViews=numViews,
                  cutOffBound=cutOffBound,
                  sleepTimes=sleepTimes,
                  repeats=repeats)

    if runRoll:
        oneTVLaws(protocol=Protocol.ROLL,
                  constFactor=2,
                  numFaults=numFaults,
                  allRepIds=allRepIds,
                  allClIds=allClIds,
                  numTransPerBlock=numTransPerBlock,
                  payloadSize=payloadSize,
                  numCl=numClients,
                  numClTrans=numClTrans,
                  numViews=numViews,
                  cutOffBound=cutOffBound,
                  sleepTimes=sleepTimes,
                  repeats=repeats)

    if runOnep:
        oneTVLaws(protocol=Protocol.ONEP,
                  constFactor=2,
                  numFaults=numFaults,
                  allRepIds=allRepIds,
                  allClIds=allClIds,
                  numTransPerBlock=numTransPerBlock,
                  payloadSize=payloadSize,
                  numCl=numClients,
                  numClTrans=numClTrans,
                  numViews=numViews,
                  cutOffBound=cutOffBound,
                  sleepTimes=sleepTimes,
                  repeats=repeats)

    if runOnepB:
        oneTVLaws(protocol=Protocol.ONEPB,
                  constFactor=2,
                  numFaults=numFaults,
                  allRepIds=allRepIds,
                  allClIds=allClIds,
                  numTransPerBlock=numTransPerBlock,
                  payloadSize=payloadSize,
                  numCl=numClients,
                  numClTrans=numClTrans,
                  numViews=numViews,
                  cutOffBound=cutOffBound,
                  sleepTimes=sleepTimes,
                  repeats=repeats)

    if runOnepC:
        oneTVLaws(protocol=Protocol.ONEPC,
                  constFactor=2,
                  numFaults=numFaults,
                  allRepIds=allRepIds,
                  allClIds=allClIds,
                  numTransPerBlock=numTransPerBlock,
                  payloadSize=payloadSize,
                  numCl=numClients,
                  numClTrans=numClTrans,
                  numViews=numViews,
                  cutOffBound=cutOffBound,
                  sleepTimes=sleepTimes,
                  repeats=repeats)

    if runOnepD:
        oneTVLaws(protocol=Protocol.ONEPD,
                  constFactor=2,
                  numFaults=numFaults,
                  allRepIds=allRepIds,
                  allClIds=allClIds,
                  numTransPerBlock=numTransPerBlock,
                  payloadSize=payloadSize,
                  numCl=numClients,
                  numClTrans=numClTrans,
                  numViews=numViews,
                  cutOffBound=cutOffBound,
                  sleepTimes=sleepTimes,
                  repeats=repeats)


    ## Chained Versions

    if runChBase or runChComb:
        terminateInstances(allRepIds + allClIds)
        (allRepIds, allClIds) = startInstances(numReps,numClientsCh)

    if runChBase:
        oneTVLaws(protocol=Protocol.CHBASE,
                  constFactor=3,
                  numFaults=numFaults,
                  allRepIds=allRepIds,
                  allClIds=allClIds,
                  numTransPerBlock=numTransPerBlock,
                  payloadSize=payloadSize,
                  numCl=numClientsCh,
                  numClTrans=numClTransCh,
                  numViews=numViews,
                  cutOffBound=cutOffBound,
                  sleepTimes=sleepTimes,
                  repeats=repeats)

    if runChComb:
        oneTVLaws(protocol=Protocol.CHCOMB,
                  constFactor=2,
                  numFaults=numFaults,
                  allRepIds=allRepIds,
                  allClIds=allClIds,
                  numTransPerBlock=numTransPerBlock,
                  payloadSize=payloadSize,
                  numCl=numClientsCh,
                  numClTrans=numClTransCh,
                  numViews=numViews,
                  cutOffBound=cutOffBound,
                  sleepTimes=sleepTimes,
                  repeats=repeats)

    terminateInstances(allRepIds + allClIds)

    createTVLplot(clientsFile,numClTrans)
    print("debug info is in", debugFile)
# End of TVLaws


def copyDamysusExperiments():
    global plotFile
    global tvlFile
    global plotBasic
    global plotChained
    global plotHandle
    global plotView
    global showYlabel
    global showLegend1
    global showLegend2
    global whichExp
    global showTitle
    global debugPlot

    showTitle = False
    debugPlot = False

    plotBasic   = True
    plotChained = True

    showYlabel  = True
    showLegend1 = True
    showLegend2 = False

    # EUregions, payload=256
    whichExp  = "EUexp1"
    pointFile = statsdir+"/points-09-Sep-2021-14:37:34.270859"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-EUregs-256B.png")

    print("--THROUGHPUT/LATENCY EU256")
    comparisonN(20,30,
                dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVChBase1,dTVChComb1,
                dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVChBase1,dLVChComb1)
    print("--")

    showYlabel  = False
    showLegend1 = False
    showLegend2 = False

    # EUregions, payload=0
    whichExp  = "EUexp1"
    pointFile = statsdir+"/points-18-Sep-2021-08:40:10.075174"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase2,dTVCheap2,dTVQuick2,dTVDamq2,dTVComb2,dTVDamr2,dTVDama2,dTVDamp2,dTVFree2,dTVRoll2,dTVOnep2,dTVOnepb2,dTVOnepc2,dTVOnepd2,dTVChBase2,dTVChComb2,
     dLVBase2,dLVCheap2,dLVQuick2,dLVDamq2,dLVComb2,dLVDamr2,dLVDama2,dLVDamp2,dLVFree2,dLVRoll2,dLVOnep2,dLVOnepb2,dLVOnepc2,dLVOnepd2,dLVChBase2,dLVChComb2) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-EUregs-0B.png")

    print("--THROUGHPUT/LATENCY EU0")
    comparisonN(20,30,
                dTVBase2,dTVCheap2,dTVQuick2,dTVDamq2,dTVComb2,dTVDamr2,dTVDama2,dTVDamp2,dTVChBase2,dTVChComb2,
                dLVBase2,dLVCheap2,dLVQuick2,dLVDamq2,dLVComb2,dLVDamr2,dLVDama2,dLVDamp2,dLVChBase2,dLVChComb2)
    print("--")

    showYlabel  = True
    showLegend1 = True
    showLegend2 = False

    # ALLregions, payload=256
    whichExp  = "ALLexp1"
    pointFile = statsdir+"/points-12-Sep-2021-21:22:48.294547-v2"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase3,dTVCheap3,dTVQuick3,dTVDamq3,dTVComb3,dTVDamr3,dTVDama3,dTVDamp3,dTVFree3,dTVRoll3,dTVOnep3,dTVOnepb3,dTVOnepc3,dTVOnepd3,dTVChBase3,dTVChComb3,
     dLVBase3,dLVCheap3,dLVQuick3,dLVDamq3,dLVComb3,dLVDamr3,dLVDama3,dLVDamp3,dLVFree3,dLVRoll3,dLVOnep3,dLVOnepb3,dLVOnepc3,dLVOnepd3,dLVChBase3,dLVChComb3) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-ALLregs-256B.png")

    print("--THROUGHPUT/LATENCY ALL256")
    comparisonN(20,30,
                dTVBase3,dTVCheap3,dTVQuick3,dTVDamq3,dTVComb3,dLVDamr3,dLVDama3,dLVDamp3,dTVChBase3,dTVChComb3,
                dLVBase3,dLVCheap3,dLVQuick3,dLVDamq3,dLVComb3,dLVDamr3,dLVDama3,dLVDamp3,dLVChBase3,dLVChComb3)
    print("--")

    showYlabel  = False
    showLegend1 = False
    showLegend2 = False

    # ALLregions, payload=0
    whichExp  = "ALLexp1"
    pointFile = statsdir+"/points-23-Sep-2021-20:57:01.200810-v2"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase4,dTVCheap4,dTVQuick4,dTVDamq4,dTVComb4,dTVDamr4,dTVDama4,dTVDamp4,dTVFree4,dTVRoll4,dTVOnep4,dTVOnepb4,dTVOnepc4,dTVOnepd4,dTVChBase4,dTVChComb4,
     dLVBase4,dLVCheap4,dLVQuick4,dLVDamq4,dLVComb4,dLVDamr4,dLVDama4,dLVDamp4,dLVFree4,dLVRoll4,dLVOnep4,dLVOnepb4,dLVOnepc4,dLVOnepd4,dLVChBase4,dLVChComb4) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-ALLregs-0B.png")

    print("--THROUGHPUT/LATENCY ALL0")
    comparisonN(20,30,
                dTVBase4,dTVCheap4,dTVQuick4,dTVDamq4,dTVComb4,dTVDamr4,dTVDama4,dTVDamp4,dTVChBase4,dTVChComb4,
                dLVBase4,dLVCheap4,dLVQuick4,dLVDamq4,dLVComb4,dLVDamr4,dLVDama4,dLVDamp4,dLVChBase4,dLVChComb4)
    print("--")

    # TVL - EUregions, payload=0, chained
    plotBasic   = False
    plotChained = True
    clientsFile = statsdir+"/clients-04-Oct-2021-12:11:35.605162"
    tvlFile  = statsdir + "/tvl-" + timestampStr + ".png"
    createTVLplot(clientsFile,-1)
    copyfile(tvlFile,"../figures/tvl-chained-EUregs-0B.png")

    # TVL - EUregions, payload=0, basic
    plotBasic   = True
    plotChained = False
    clientsFile = statsdir+"/clients-06-Oct-2021-03:11:36.399919"
    tvlFile  = statsdir + "/tvl-" + timestampStr + ".png"
    createTVLplot(clientsFile,-1)
    copyfile(tvlFile,"../figures/tvl-basic-EUregs-0B.png")

    showYlabel  = True
    showLegend1 = True
    showLegend2 = False

    # ONEregion, payload=0
    whichExp  = "ONEexp1"
    pointFile = statsdir+"/points-08-Sep-2022-combined"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-ONEreg-0B.png")

    # ONEregion, payload=256
    whichExp  = "ONEexp1"
    pointFile = statsdir+"/points-16-Sep-2022-combined"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-ONEreg-256B.png")

    plotHandle = True
    plotView   = False

    # ONEregion, payload=0 -- handleonly
    whichExp  = "ONEexp1"
    pointFile = statsdir+"/points-08-Sep-2022-combined"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-ONEreg-0B-handle.png")

    # ONEregion, payload=256 --handleonly
    whichExp  = "ONEexp1"
    pointFile = statsdir+"/points-16-Sep-2022-combined"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-ONEreg-256B-handle.png")


def copyOneShotExperiments():
    global plotFile
    global tvlFile
    global plotBasic
    global plotChained
    global plotHandle
    global plotView
    global showYlabel
    global showLegend1
    global showLegend2
    global whichExp
    global showTitle
    global debugPlot

    # payload=0 latency=0
    pointFile = statsdir+"/points-28-Mar-2023-12:27:54.316676"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-1p-0ms-0B.png")

    # payload=0 latency=10
    pointFile = statsdir+"/points-28-Mar-2023-15:06:52.955560"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-1p-10ms-0B.png")

    # payload=0 latency=100
    pointFile = statsdir+"/points-28-Mar-2023-17:23:15.539785"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-1p-100ms-0B.png")

    # payload=256 latency=0
    pointFile = statsdir+"/points-28-Mar-2023-20:55:52.523475"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-1p-0ms-256B.png")

    # payload=256 latency=10
    pointFile = statsdir+"/points-28-Mar-2023-23:01:14.176344"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-1p-10ms-256B.png")

    # payload=256 latency=100
    pointFile = statsdir+"/points-29-Mar-2023-01:45:05.351300"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-1p-100ms-256B.png")

    # payload=256 latency=100 1/2
    pointFile = statsdir+"/points-29-Mar-2023-23:38:11.874277"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-1p-10ms-256B-50.png")

    # payload=256 latency=100 1/3
    pointFile = statsdir+"/points-29-Mar-2023-19:51:59.492672"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-1p-10ms-256B-33.png")

    # payload=256 latency=100 1/4
    pointFile = statsdir+"/points-29-Mar-2023-14:36:43.045542"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-1p-10ms-256B-25.png")

    # payload=256 latency=100 50+-50
    pointFile = statsdir+"/points-22-Mar-2023-11:00:28.123250"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-1p-50ms-50var-256B.png")


def copyOneShotAWSExperiments():
    global plotFile
    global tvlFile
    global plotBasic
    global plotChained
    global plotHandle
    global plotView
    global showYlabel
    global showLegend1
    global showLegend2
    global whichExp
    global showTitle
    global debugPlot

    # regions=US payload=0
    pointFile = statsdir+"/points-28-Sep-2023-02:24:24.406924" #"/points-13-Sep-2023-12:21:40.700210"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-1p-aws-us-0B.png")

    # regions=US payload=256
    pointFile = statsdir+"/points-29-Sep-2023-21:37:50.162903" #"/points-20-Sep-2023-23:24:32.586954"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-1p-aws-us-256B.png")

    # regions=EU payload=0
    pointFile = statsdir+"/points-22-Sep-2023-16:27:10.874357"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-1p-aws-eu-0B.png")

    # regions=EU payload=256
    pointFile = statsdir+"/points-22-Sep-2023-10:32:45.166841"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-1p-aws-eu-256B.png")

    ## NOT DONE YET
    # # regions=ONE payload=0
    # pointFile = statsdir+"/"
    # plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    # (dTVBase1,dTVCheap1,dTVQuick1,dTVComb1,dTVFree1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,dLVBase1,dLVCheap1,dLVQuick1,dLVComb1,dLVFree1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    # copyfile(plotFile,"../figures/eval-1p-aws-one-0B.png")

    # regions=ONE payload=256
    pointFile = statsdir+"/points-24-Sep-2023-20:46:37.931370"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-1p-aws-one-256B.png")

    # regions=ALL payload=0
    pointFile = statsdir+"/points-26-Sep-2023-18:10:17.577236"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-1p-aws-all-0B.png")

    # regions=ALL payload=256
    pointFile = statsdir+"/points-27-Sep-2023-12:23:37.655408"
    plotFile  = statsdir + "/plot-" + timestampStr + ".png"
    (dTVBase1,dTVCheap1,dTVQuick1,dTVDamq1,dTVComb1,dTVDamr1,dTVDama1,dTVDamp1,dTVFree1,dTVRoll1,dTVOnep1,dTVOnepb1,dTVOnepc1,dTVOnepd1,dTVChBase1,dTVChComb1,
     dLVBase1,dLVCheap1,dLVQuick1,dLVDamq1,dLVComb1,dLVDamr1,dLVDama1,dLVDamp1,dLVFree1,dLVRoll1,dLVOnep1,dLVOnepb1,dLVOnepc1,dLVOnepd1,dLVChBase1,dLVChComb1) = createPlot(pointFile)
    copyfile(plotFile,"../figures/eval-1p-aws-all-256B.png")


def setRegion(reg):
    global regions
    if reg == ONEregionsNAME:
        regions = (ONEregionsNAME, ONEregions)
    elif reg == EUregionsNAME:
        regions = (EUregionsNAME, EUregions)
    elif reg == USregionsNAME:
        regions = (USregionsNAME, USregions)
    elif reg == ALLregionsNAME:
        regions = (ALLregionsNAME, ALLregions)
    elif reg == ALL2regionsNAME:
        regions = (ALL2regionsNAME, ALL2regions)
    elif reg == ALL3regionsNAME:
        regions = (ALL3regionsNAME, ALL3regions)
    else:
        # default
        regions = (ONEregionsNAME, ONEregions)


parser = argparse.ArgumentParser(description='X-HotStuff evaluation')
parser.add_argument("--file",       help="file to plot", type=str, default="")
parser.add_argument("--pfile",      help="file to plot", type=str, default="")
parser.add_argument("--jfile",      help="file to plot", type=str, default="")
parser.add_argument("--jfile2",     help="file to plot", type=str, default="")
parser.add_argument("--conf",       type=int, default=0)     # generate a configuration file for 'n' nodes
parser.add_argument("--tvl",        action="store_true")     # throughput vs. latency experiments
parser.add_argument("--tvlaws",     action="store_true")     # throughput vs. latency experiments on AWS
parser.add_argument("--launch",     type=int, default=0)     # launch EC2 instances
parser.add_argument("--aws",        action="store_true")     # run AWS
parser.add_argument("--cluster",    action="store_true")     # run cluster
parser.add_argument("--prepare",    action="store_true")     # prepare cluster
parser.add_argument("--containers", type=int, default=0)     # launch Docker instances
parser.add_argument("--awstest",    action="store_true")     # test AWS
parser.add_argument("--stop",       action="store_true")     # to terminate all instances in the current region
parser.add_argument("--stopall",    action="store_true")     # to terminate all instances in all regions
parser.add_argument("--latest",     type=int, default=0,   help="copies plots")     # copies latest experiments to paper
parser.add_argument("--copy",       type=str, default="",  help="copies all files to the AWS address provided as argument")
parser.add_argument("--nocopy",     action="store_true",   help="does not copy the files when running the AWS experiments")
parser.add_argument("--docker",     action="store_true",   help="runs nodes locally in Docker containers")
parser.add_argument("--das5",       action="store_true",   help="runs nodes natively on DAS-5 nodes allocated by SLURM")
parser.add_argument("--das5-address-cmd", type=str, default="hostname -f", help="command run on each DAS-5 node to obtain the address written to config")
parser.add_argument("--randomize",  action="store_true",   help="randomizes AWS regions before allocating nodes to regions")
parser.add_argument("--repeats",    type=int, default=0,   help="number of repeats per experiment")
parser.add_argument("--repeats2",   type=int, default=0,   help="number of repeats per experiment (2nd level, i.e., regenerates AWS instances)")
parser.add_argument("--faults",     type=str, default="",  help="the number of faults to test, separated by commas: 1,2,3,etc.")
parser.add_argument("--test",       action="store_true",   help="to stop after checking the arguments")
parser.add_argument("--payload",    type=int, default=0,   help="size of payloads in Bytes")
parser.add_argument("--p1",         action="store_true",   help="sets runBase to True (base protocol, i.e., HotStuff)")
parser.add_argument("--p2",         action="store_true",   help="sets runCheap to True (Damysus-C)")
parser.add_argument("--p3",         action="store_true",   help="sets runQuick to True (Damysus-A)")
parser.add_argument("--p4",         action="store_true",   help="sets runComb to True (Damysus)")
parser.add_argument("--np4",        action="store_true",   help="sets runComb to False (Damysus)")
parser.add_argument("--p5",         action="store_true",   help="sets runChBase to True (chained base protocol, i.e., chained HotStuff")
parser.add_argument("--p6",         action="store_true",   help="sets runChComb to True (chained Damysus)")
parser.add_argument("--p7",         action="store_true",   help="sets runFree to True (hash&signature-free Damysus)")
parser.add_argument("--p7b",        action="store_true",   help="sets runDamr to True (hash&signature-free Damysus + kinda ROTE)")
parser.add_argument("--p7c",        action="store_true",   help="sets runDamp to true (hash&signature-free Damysus + Pacemaker)")
parser.add_argument("--p7d",        action="store_true",   help="sets runDamq to True (hash&signature-free Damysus + Pacemaker + 3f+1 nodes)")
parser.add_argument("--p7e",        action="store_true",   help="sets runDama to True (hash&signature-free Damysus + kinda Achilles)")
parser.add_argument("--p8",         action="store_true",   help="sets runOnep to True (1+1/2 phase Damysus)")
parser.add_argument("--p8b",        action="store_true",   help="sets runOnepB to True (1+1/2 phase Damysus)")
parser.add_argument("--p8c",        action="store_true",   help="sets runOnepC to True (1+1/2 phase Damysus)")
parser.add_argument("--p8d",        action="store_true",   help="sets runOnepD to True (1+1/2 phase Damysus)")
parser.add_argument("--p9",         action="store_true",   help="with rollback prevention")
parser.add_argument("--pall",       action="store_true",   help="sets all runXXX to True, i.e., all protocols will be executed")
parser.add_argument("--netlat",     type=float, default=0, help="network latency in ms")
#parser.add_argument("--netlat",     type=int, default=0,   help="network latency in ms")
parser.add_argument("--netvar",     type=int, default=0,   help="variation of the network latency in ms")
parser.add_argument("--clients1",   type=int, default=0,   help="number of clients for the non-chained versions")
parser.add_argument("--clients2",   type=int, default=0,   help="number of clients for the chained versions")
parser.add_argument("--onecore",    action="store_true",   help="sets useMultiCores to False, i.e., use 1 core only to compile")
parser.add_argument("--hw",         action="store_true",   help="sets sgxmode to HW, i.e., sgx will be used in hardware mode")
parser.add_argument("--memory",     type=int, default=0,   help="memory used by docker containers")
parser.add_argument("--cpus",       type=float, default=0, help="cpus used by docker containers")
parser.add_argument("--nocompil",   action="store_true",   help="to not recompile the code at the beginnong of each experiment (should only be used when runnning an already compiled experiment)")
parser.add_argument("--cutoff",     type=int, default=0,   help="time after which the experiments are stopped (in seconds)")
parser.add_argument("--views",      type=int, default=0,   help="number of views to run per experiments")
parser.add_argument("--regions",    type=str, default="",  help="the AWS regions to use (one, eu, us, all)")
parser.add_argument("--handle",     action="store_true",   help="to plot handling times")
parser.add_argument("--handleonly", action="store_true",   help="to plot handling times only")
parser.add_argument("--crypto",     action="store_true",   help="to plot crypto times")
parser.add_argument("--cryptoonly", action="store_true",   help="to plot crypto times only")
parser.add_argument("--debug",      type=int, default=1,   help="to print debugging information while plotting (0 means no)")
parser.add_argument("--latency",    type=int, default=1,   help="to not print debugging information while plotting (0 means no)")
parser.add_argument("--throughput", type=int, default=1,   help="to not print debugging information while plotting (0 means no)")
parser.add_argument("--nodisplay",  action="store_true",   help="do not open generated plots in an image viewer")
parser.add_argument("--rate",       type=int, default=0,   help="bandwidth when using netem")
parser.add_argument("--trans",      type=int, default=0,   help="number of transactions per block")
parser.add_argument("--timeout",    type=int, default=0,   help="timeout before starting a new view (in seconds)")
parser.add_argument("--timeoutMul", type=int, default=0,   help="factor used to mulitply the timeout with when timeouts occur")
parser.add_argument("--timeoutDiv", type=int, default=0,   help="factor used to divide the timeout with when making progress")
parser.add_argument("--opdist",     type=int, default=0,   help="OP cases")
parser.add_argument("--dead",       type=int, nargs='?', const=1, default=-1, help="start with N dead replicas (default 1 if no value)")
parser.add_argument("--syncperiod", type=int, default=0,   help="synchronization period")
parser.add_argument("--joinperiod", type=int, default=0,   help="joining period")
parser.add_argument("--joining",    action="store_true",   help="to run experiments varying the number of joining nodes (rollback-resilient protocol)")
parser.add_argument("--numjoiners", type=str, default="",  help="number of nodes to join")
parser.add_argument("--quantile1",  type=int, default=0,   help="quantile1")
parser.add_argument("--quantile2",  type=int, default=0,   help="quantile2")
parser.add_argument("--skip",       type=int, default=0,   help="number of views to skip at the start of a run")
parser.add_argument("--loss",       type=int, default=0,   help="percentage of messages lost using netem in docker")
parser.add_argument("--stress",     action="store_true",   help="runs stress-ng")


args = parser.parse_args()


if args.regions:
    if args.regions in [ONEregionsNAME,EUregionsNAME,USregionsNAME,ALLregionsNAME,ALL2regionsNAME,ALL3regionsNAME]:
        setRegion(args.regions)
        print("SUCCESSFULLY PARSED ARGUMENT - regions is", args.regions)
    else:
        print("UNSUCCESSFULLY PARSED regions ARGUMENT")


if args.quantile1 > 0:
    quantileSize1 = args.quantile1
    print("SUCCESSFULLY PARSED ARGUMENT - quantileSize1 is now:", quantileSize1)


if args.quantile2 > 0:
    quantileSize2 = args.quantile2
    print("SUCCESSFULLY PARSED ARGUMENT - quantileSize2 is now:", quantileSize2)


if args.skip > 0:
    skipViews = args.skip
    print("SUCCESSFULLY PARSED ARGUMENT - skipViews is now:", skipViews)


if args.loss > 0:
    msgLoss = args.loss
    print("SUCCESSFULLY PARSED ARGUMENT - msgLoss is now:", msgLoss)


if args.syncperiod > 0:
    syncPeriod = args.syncperiod
    print("SUCCESSFULLY PARSED ARGUMENT - synchronization period is now:", syncPeriod)


if args.joinperiod > 0:
    joinPeriod = args.joinperiod
    print("SUCCESSFULLY PARSED ARGUMENT - joining period is now:", joinPeriod)


if args.stress:
    stressNg = True
    print("SUCCESSFULLY PARSED ARGUMENT - stressNg now:", stressNg)


if args.nodisplay:
    displayPlot = False
    print("SUCCESSFULLY PARSED ARGUMENT - generated plots will not be opened")


if args.numjoiners:
    l = list(map(lambda x: int(x), args.numjoiners.split(",")))
    numJoiners = l[0]
    print("SUCCESSFULLY PARSED ARGUMENT - number of joiners is now:", numJoiners)


if args.timeout > 0:
    timeout = args.timeout
    print("SUCCESSFULLY PARSED ARGUMENT - timeout is now:", timeout , "seconds")


if args.timeoutMul > 0:
    timeoutMul = args.timeoutMul
    print("SUCCESSFULLY PARSED ARGUMENT - timeoutMul is now:", timeoutMul)


if args.timeoutDiv > 0:
    timeoutDiv = args.timeoutDiv
    print("SUCCESSFULLY PARSED ARGUMENT - timeoutDiv is now:", timeoutDiv)


if args.opdist > 0:
    opdist = args.opdist
    print("SUCCESSFULLY PARSED ARGUMENT - opdist is now:", opdist)


if args.dead >= 0:
    numDeadNodesCfg = args.dead
    deadNodes = (numDeadNodesCfg > 0)
    print("SUCCESSFULLY PARSED ARGUMENT - number of dead replicas at startup:", numDeadNodesCfg)


if args.rate > 0:
    rateMbit = args.rate
    print("SUCCESSFULLY PARSED ARGUMENT - rate is now:", rateMbit)


if args.trans > 0:
    numTrans = args.trans
    print("SUCCESSFULLY PARSED ARGUMENT - number of transactions per block is now:", numTrans)


if args.views > 0:
    numViews = args.views
    print("SUCCESSFULLY PARSED ARGUMENT - the number of views is now:", numViews)


if args.cutoff > 0:
    cutOffBound = args.cutoff
    print("SUCCESSFULLY PARSED ARGUMENT - the cutoff bound is now:", cutOffBound)


if args.repeats > 0:
    repeats = args.repeats
    print("SUCCESSFULLY PARSED ARGUMENT - the number of repeats is now:", repeats)


if args.repeats2 > 0:
    repeatsL2 = args.repeats2
    print("SUCCESSFULLY PARSED ARGUMENT - the number of 2nd level repeats is now:", repeatsL2)


if args.memory > 0:
    dockerMem = args.memory
    print("SUCCESSFULLY PARSED ARGUMENT - the memory used by docker containers is now (in MB):", dockerMem)


if args.cpus > 0:
    dockerCpu = args.cpus
    print("SUCCESSFULLY PARSED ARGUMENT - the cpus used by docker containers is now:", dockerCpu)


if args.netlat >= 0:
    networkLat = args.netlat
    print("SUCCESSFULLY PARSED ARGUMENT - the network latency (in ms) will be changed using netem to:", networkLat)


if args.netvar >= 0:
    networkVar = args.netvar
    print("SUCCESSFULLY PARSED ARGUMENT - the variation of the network latency (in ms) will be changed using netem to:", networkVar)


if args.payload >= 0:
    payloadSize = args.payload
    print("SUCCESSFULLY PARSED ARGUMENT - the payload size will be:", payloadSize)


if args.docker:
    runDocker = True
    print("SUCCESSFULLY PARSED ARGUMENT - running nodes in Docker containers")


if args.das5:
    runDas5 = True
    das5AddressCmd = args.das5_address_cmd
    if runDocker:
        raise RuntimeError("--das5 cannot be combined with --docker")
    if not slurmAvailable():
        print("WARNING: --das5 was selected, but SLURM_JOB_ID is not set; run through sbatch or salloc on DAS-5")
    print("SUCCESSFULLY PARSED ARGUMENT - running nodes natively on DAS-5 via SLURM")
    print("SUCCESSFULLY PARSED ARGUMENT - DAS-5 address command is:", das5AddressCmd)


if args.randomize:
    randomizeRegions = True
    print("SUCCESSFULLY PARSED ARGUMENT - randomizing AWS regions before allocating nodes")


if args.nocompil:
    recompile = False
    print("SUCCESSFULLY PARSED ARGUMENT - will not re-compile the code")


if args.handle:
    plotHandle = True
    print("SUCCESSFULLY PARSED ARGUMENT - will plot handling time")


if args.crypto:
    plotCrypto = True
    print("SUCCESSFULLY PARSED ARGUMENT - will plot crypto time")


if args.handleonly:
    plotHandle = True
    plotView   = False
    print("SUCCESSFULLY PARSED ARGUMENT - will plot handling time only")


if args.cryptoonly:
    plotCrypto = True
    plotView   = False
    print("SUCCESSFULLY PARSED ARGUMENT - will plot crypto time only")


if 0 <= args.debug:
    if args.debug == 0:
        debugPlot = False
        print("SUCCESSFULLY PARSED ARGUMENT - will not print debugging info while plotting")
    else:
        debugPlot = True
        print("SUCCESSFULLY PARSED ARGUMENT - will print debugging info while plotting")


if 0 <= args.latency:
    if args.latency == 0:
        plotLatency = False
        print("SUCCESSFULLY PARSED ARGUMENT - will not plot latency")
    else:
        plotLatency = True
        print("SUCCESSFULLY PARSED ARGUMENT - will plot latency")


if 0 <= args.throughput:
    if args.throughput == 0:
        plotThroughput = False
        print("SUCCESSFULLY PARSED ARGUMENT - will not plot throughput")
    else:
        plotThroughput = True
        print("SUCCESSFULLY PARSED ARGUMENT - will plot throughput")


if args.onecore:
    useMultiCores = False
    print("SUCCESSFULLY PARSED ARGUMENT - will use 1 core only to compare")


if args.hw:
    sgxmode = "HW"
    print("SUCCESSFULLY PARSED ARGUMENT - SGX will be used in hardware mode")


if args.faults:
    l = list(map(lambda x: int(x), args.faults.split(",")))
    faults = l
    print("SUCCESSFULLY PARSED ARGUMENT - we will be testing for f in", l)


if args.p1:
    runBase = True
    print("SUCCESSFULLY PARSED ARGUMENT - testing base protocol")

if args.p2:
    runCheap = True
    print("SUCCESSFULLY PARSED ARGUMENT - testing Damysus-C")

if args.p3:
    runQuick = True
    print("SUCCESSFULLY PARSED ARGUMENT - testing Damysus-A")

if args.p4:
    runComb = True
    print("SUCCESSFULLY PARSED ARGUMENT - testing Damysus")

if args.np4:
    plotComb = False
    print("SUCCESSFULLY PARSED ARGUMENT - not ploting Damysus")

if args.p5:
    runChBase = True
    print("SUCCESSFULLY PARSED ARGUMENT - testing chained base protocol")

if args.p6:
    runChComb = True
    print("SUCCESSFULLY PARSED ARGUMENT - testing chained Damysus")

if args.p7:
    runFree = True
    print("SUCCESSFULLY PARSED ARGUMENT - testing hash&signature-free Damysus")

if args.p7b:
    runDamr = True
    print("SUCCESSFULLY PARSED ARGUMENT - testing hash&signature-free Damysus + kinda ROTE")

if args.p7c:
    runDamp = True
    print("SUCCESSFULLY PARSED ARGUMENT - testing Damysus + Pacemaker")

if args.p7d:
    runDamq = True
    print("SUCCESSFULLY PARSED ARGUMENT - testing Damysus + Pacemaker + 3f+1 nodes")

if args.p7e:
    runDama = True
    print("SUCCESSFULLY PARSED ARGUMENT - testing hash&signature-free Damysus + kinda Achilles")

if args.p8:
    runOnep = True
    print("SUCCESSFULLY PARSED ARGUMENT - testing 1+1/2 phase Damysus")

if args.p8b:
    runOnepB = True
    print("SUCCESSFULLY PARSED ARGUMENT - testing 1+1/2 phase Damysus (case 2)")

if args.p8c:
    runOnepC = True
    print("SUCCESSFULLY PARSED ARGUMENT - testing 1+1/2 phase Damysus (case 3)")

if args.p8d:
    runOnepD = True
    print("SUCCESSFULLY PARSED ARGUMENT - testing 1+1/2 phase Damysus (case 4)")

if args.p9:
    runRoll = True
    print("SUCCESSFULLY PARSED ARGUMENT - testing rollback prevention")

if args.pall:
    runBase   = True
    runCheap  = True
    runQuick  = True
    runDamq   = True
    runComb   = True
    runDamr   = True
    runDama   = True
    runDamp   = True
    runFree   = True
    runRoll   = True
    runOnep   = True
    runOnepB  = True
    runOnepC  = True
    runOnepD  = True
    runChBase = True
    runChComb = True
    print("SUCCESSFULLY PARSED ARGUMENT - testing all protocols")


if args.clients1 > 0:
    numNonChCls = args.clients1
    print("SUCCESSFULLY PARSED ARGUMENT - the number of clients for the non-chained version is now:", numNonChCls)


if args.clients2 > 0:
    numChCls = args.clients2
    print("SUCCESSFULLY PARSED ARGUMENT - the number of clients for the chained version is now:", numChCls)

if args.nocopy:
    copyAll = False
    print("SUCCESSFULLY PARSED ARGUMENT - files will not be copied for AWS experiment")

if args.test:
    print("done")
elif args.file.startswith(statsdir+"/points-") or args.file.startswith(statsdir+"/final-points-"):
    createPlot(args.file)
elif args.file.startswith(statsdir+"/clients-"):
    createTVLplot(args.file,-1)
elif args.pfile.startswith(statsdir+"/points-") or args.pfile.startswith(statsdir+"/final-points-"):
    l = args.pfile.split(",")
    createPlotPayload(l)
elif args.jfile.startswith(statsdir+"/points-") or args.jfile.startswith(statsdir+"/final-points-"):
    joining = True
    createPlotJoin(args.jfile)
elif args.jfile2.startswith(statsdir+"/points-") or args.jfile2.startswith(statsdir+"/final-points-"):
    joining = True
    createPlotJoin2(args.jfile2)
elif args.file.startswith(statsdir+"/view-times-"):
    createPlotViewTimes(args.file)
elif args.conf > 0:
    genLocalConf(args.conf,addresses)
elif args.tvl:
    print("Throughput vs. Latency")
    TVL()
elif args.tvlaws:
    print("Throughput vs. Latency")
    TVLaws()
elif args.launch:
    print("lauching AWS instances")
    startInstances(args.launch,0)
elif args.containers:
    print("lauching Docker containers")
    numContainers = args.containers
    startContainers(numContainers,0)
    prot = Protocol.ONEP
    fact = 2
    if args.p1:
        prop = Protocol.BASE
        fact = 3
    elif args.p2:
        prop = Protocol.CHEAP
        fact = 2
    elif args.p3:
        prop = Protocol.QUICK
        fact = 3
    elif args.p4:
        prop = Protocol.COMB
        fact = 2
    elif args.p5:
        prop = Protocol.CHBASE
        fact = 3
    elif args.p6:
        prop = Protocol.CHCOMB
        fact = 2
    elif args.p7:
        prop = Protocol.FREE
        fact = 2
    elif args.p7b:
        prop = Protocol.DAMR
        fact = 2
    elif args.p7c:
        prop = Protocol.DAMP
        fact = 2
    elif args.p7d:
        prop = Protocol.DAMQ
        fact = 3
    elif args.p7e:
        prop = Protocol.DAMA
        fact = 2
    elif args.p8:
        prop = Protocol.ONEP
        fact = 2
    elif args.p8b:
        prop = Protocol.ONEPB
        fact = 2
    elif args.p8c:
        prop = Protocol.ONEPC
        fact = 2
    elif args.p8d:
        prop = Protocol.ONEPD
        fact = 2
    elif args.p9:
        prop = Protocol.ROLL
        fact = 2
    else:
        prop = Protocol.ONEP
        fact = 2
    mkParams(protocol=prot,constFactor=fact,numFaults=1,numTrans=400,payloadSize=0)
    for i in range(numContainers):
        instance = dockerBase + str(i)
        src = "Makefile"
        dst = instance + ":/app/"
        subprocess.run([docker + " cp " + src + " " + dst], shell=True, check=True)
        src =  "App/."
        dst = instance + ":/app/App/"
        subprocess.run([docker + " cp " + src + " " + dst], shell=True, check=True)
        src =  "Enclave/."
        dst = instance + ":/app/Enclave/"
        subprocess.run([docker + " cp " + src + " " + dst], shell=True, check=True)
        subprocess.run([docker + " exec -t " + instance + " bash -c \"" + srcsgx + "; make clean; make -j " + str(1) + " SGX_MODE=" + sgxmode + "\""], shell=True, check=True)
elif args.copy:
    print("copying files to AWS instance")
    copyToAddr(args.copy)
elif args.awstest:
    print("AWS")
    testAWS()
elif args.aws:
    print("lauching AWS experiment")
    if args.joining and args.numjoiners:
        print("...in joining mode")
        joining = True
        joiners = list(map(lambda x: int(x), args.numjoiners.split(",")))
        if len(joiners) == 1:
            joiners = range(numJoiners+1)
        if len(faults) > 0:
            runAWSJoin(faults[0],joiners)
        else:
            runAWSJoin(2,joiners)
    else:
        runAWS()
elif args.cluster:
    print("lauching cluster experiment")
    runCluster()
elif args.prepare:
    print("preparing cluster")
    prepareCluster()
elif args.stop:
    print("terminate all AWS instances in the current region")
    terminateAllInstances()
elif args.stopall:
    print("terminate all AWS instances in all regions")
    terminateAllInstancesAllRegs()
elif args.latest > 0:
    print("copies latest experiments to paper")
    debugPlot = False
    if args.latest == 1:
        copyDamysusExperiments()
    elif args.latest == 2:
        copyOneShotExperiments()
    else:
        copyOneShotAWSExperiments()
elif args.dead >= 0:
    runExperiments()
elif args.joining and args.numjoiners:
    joining = True
    joiners = list(map(lambda x: int(x), args.numjoiners.split(",")))
    if len(joiners) == 1:
        joiners = range(numJoiners+1)
    if len(faults) > 0:
        runExperimentsJoin(faults[0],joiners)
    else:
        runExperimentsJoin(2,joiners) # some random default value so that we have a few points
else:
    print("Throughput and Latency")
    runExperiments()


#### Run the experiments to compute throughputs & latencies
#runExperiments()

## Debug
#tup = computeAvgStats(recompile=False,protocol=Protocol.COMB,constFactor=2,numFaults=1,numRepeats=1)
#print(tup)
#createPlot(plotFile)
#createPlot("points-01-Apr-2021-15:48:12.821672")
#createPlot("stats/points-08-Apr-2021-15:57:31.873203")
#mkApp(protocol=Protocol.CHEAP,constFactor=2,numFaults=1,numTrans=numTrans,payloadSize=payloadSize)
#createPlot("stats/points-13-Apr-2021-10:18:28.616683")
#createPlot("stats/points-14-Apr-2021-10:58:41.589782")
#createPlot("stats/points-15-Apr-2021-01:10:01.920476")

#### Run the experiments to compute throughput vs. latency
#TVL()

## Debug
#createTVLplot("stats/clients-10-Apr-2021-00:44:17.638744")
#createTVLplot("stats/clients-15-Apr-2021-02:40:47.929625")

