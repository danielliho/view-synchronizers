# DAMYSUS: Streamlined BFT Consensus Leveraging Trusted Components

This is the accompanying code to the paper "DAMYSUS: Streamlined BFT
Consensus Leveraging Trusted Components" which was accepted to EuroSys
2022. A technical report is available
[here](https://github.com/vrahli/damysus/blob/main/doc/damysus-extended.pdf).

## Current status

The software is under ongoing development.

## Installing

To tests our protocols, we provide a Python script, called
`experiments.py`, as well as a `Dockerfile` to create a Docker
container. We use the
[Salticidae](https://github.com/Determinant/salticidae) library, which
is added here as git submodule.

### Salticidae

You won't need to follow this step if you are using our Docker
container, as it is done when building the container, and can jump to
the next (Python) section.
If you decide to install Salticidae locally, you will need git and cmake.
In which case, after cloning the repository you need to type this to initialize the
Salticidae git submodule:

`git submodule init`

followed by:

`git submodule update`

Salticidea has the following dependencies:

* CMake >= 3.9
* C++14
* libuv >= 1.10.0
* openssl >= 1.1.0

`sudo apt install cmake libuv1-dev libssl-dev`

Then, to instance Salticidae, type:
`(cd salticidae; cmake . -DCMAKE_INSTALL_PREFIX=.; make; make install)`

### Python

We use python version 3.13.3.  You will need python3-pip to install
the required modules.

The Python script relies on the following modules:
- subprocess
- pathlib
- matplotlib
- time
- math
- os
- glob
- datetime
- argparse
- enum
- json
- multiprocessing
- random
- shutil
- re

If you haven't installed those modules yet, run:

`python3 -m pip install subprocess pathlib matplotlib time math os glob datetime argparse enum json multiprocessing random shutil re`

### Docker

To run the experiments within Docker containers, you need to have
installed Docker on your machine. This
[page](https://docs.docker.com/engine/install/) explains how to
install Docker. In particular follow the following
[instructions](https://docs.docker.com/engine/install/linux-postinstall/)
so that you can run Docker as a non-root user.

You then need to create the container by typing the following command at the root of the project:

`docker build -f Dockerfile2 -t damysus2 .`

This will create a container called `damysus2`.

We use `jq` to extract the IP addresses of Docker containers, so make
sure to install that too.



## Usage

### Default command

We explain the various options our Python scripts provides. You will
run commands of the following form, followed by various options
explained below:

`python3 experiments.py --docker --pall`

### Options

In addition, you can use the following options to change some of the parameters:
- `--docker` to run the nodes within Docker containers
- `--repeats n` to change the number of repeats per experiment to `n`
- `--payload n` to change the payload size to `n`
- `--faults a,b,c` to run the experiments for f=a, f=b, etc.
- `--pall` is to run all protocols, instead you can use `--p1` up to `--p6`
    - `--p1`: base protocol, i.e., HotStuff
    - `--p2`: Damysus-C (checker only)
    - `--p3`: Damysus-A (accumulator only)
    - `--p4`: Damysus
    - `--p5`: chained base protocol, i.e., chained HotStuff
    - `--p6`: chained Damysus
    - `--p7`: hash & signature-free Damysus
    - `--p8`: OneShot
    - `--p9`: Athena
- `--netlat n` to change the network latency to `n`ms
- `--clients1 n` to change the number of clients to `n` for the non-chained protocols
- `--clients2 n` to change the number of clients to `n` for the chained protocols
- `--tvl` to compute a "max throughput" graph
- `--onecore` to compute the code using one core only
- `--hw` to run SGX in hardware mode
    + this option cannot be used with docker
    + it requires the sgxsdk to be installed here: `/opt/intel/sgxsdk`, which can be achieved following the steps in the Dockerfile
    + it requires installing Salticidae following the steps mentioned above
- `--cluster` to run the nodes remotely (see the [Cluster](###Cluster) section for more information)
    + this option will automatically use Docker containers
    + it currently cannot user SGX in hardware mode
    + it currently cannot be combined with `--tvl`

### Examples

For example, if you run:

`python3 experiments.py --docker --p9 --repeats 2 --faults 1,2`

then you will run the replicas within Docker containers (`--docker`),
test Athena (`--p9`) only, repeat the experiment twice (` --repeats
2`) for both f+u=1 and f+u=2 (`--faults 2`).
