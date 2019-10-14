# Introduction
This project has been used and tested on Raspberry Pi (RPi) 4 running Raspbian Buster Lite, kernel version 4.19 (there is no reason preventing it from working on other RPi model). It does two things:

1. Use `tcpdump` to sniff WiFi probe request based on an open source tool [`sniff-probes`](https://github.com/brannondorsey/sniff-probes). The `sniff-probes` module used in the current repo is a fork of the original version, but with major modification to suit the needs of the current project.
2. Parse the probe request output from `tcpdump` and store them in a local SQLite database at any given interval (i.e. duration of a monitor session).

# Usage
## 1. Find WiFi Chip with Monitor Mode.
For example, if Raspberry Pi (RPi) is used, one can use Kali Linux or follow [nexmon](https://github.com/seemoo-lab/nexmon) enable monitor mode of RPi's own WiFi chip. However, we do not recommend this method, because monitor mode RPi's own WiFi chip is not stable, especially during channel hopping. This problem of inconsistent WiFi chip crash when set in monitor mode has been widely reported. If user still wishes to hack RPi's own WiFi chip into monitor mode, he/she must exercise caution and expect potential hardware problems. 

We recommend investing in a WiFi adaptor that supports monitor mode. For RPi use, one can refer to this [purchase guide](https://null-byte.wonderhowto.com/how-to/buy-best-wireless-network-adapter-for-wi-fi-hacking-2019-0178550/) and this [field test report](https://null-byte.wonderhowto.com/how-to/select-field-tested-kali-linux-compatible-wireless-adapter-0180076/) to make informed decision. We choose to use [Alfa AWUS036NHA](https://store.rokland.com/products/alfa-awus036nha-802-11n-wireless-n-usb-wi-fi-adapter-2-watt), which serves its purpose well so far.

## 2. Enable Monitor Mode on a WiFi Interface
Run command `sudo iwconfig` to see all the WiFi interface currently available on a RPi. RPi's own WiFi interface is usually at `wlan0`. If you use Kali Linux or `nexmon`, then `wlan0` is the interface for monitor mode. If, on the other hand, you plug in a WiFi adaptor, then most likely `wlan1` will be the interface for the adaptor and hence monitor mode.

Once identified, run the following command to enable monitor mode (here, we will use `wlan1` as example)

```
sudo ifconfig wlan1 down
sudo iwconfig wlan1 mode monitor
sudo ifconfig wlan1 up
```
To check whether monitor mode has been successfully enabled on `wlan1`, run `iwconfig` to see whether the mode for `wlan1` has switched from `Managed` to `Monitor`. The following is our output after monitor mode is set up.

```
$ iwconfig
...
wlan1     IEEE 802.11  Mode:Monitor  Frequency:2.437 GHz  Tx-Power=20 dBm
          Retry short limit:7   RTS thr:off   Fragment thr:off
          Power Management:off
```
## 3. Install System Dependencies
If SQLite has not been installed yet, run the following command to install: `sudo apt-get install sqlite3`

If tcpdump has not been installed yet, run the following command to install: `sudo apt-get install tcpdump`

## 4. Clone This Repo
Note that since a submodule `sniff-probes` is used in this repo, we must initiate and update the submodule as well when cloning. Run the following command and read more about git submodule [here](https://git-scm.com/book/en/v2/Git-Tools-Submodules)

`git clone --recurse-submodules https://github.com/I-SENSE/Mobintel.git`

## 5. Install Python Dependency
First make sure you have `pipenv` installed. If not, run `sudo apt-get install pipenv` to install it for Raspbian.

Then go to `gatherer` directory and run `pipenv install`. This will install the dependencies (you can see all the dependencies in Pipfile, which currently includes `pyyaml` and `pyinstaller`).

## 6. Run Program
Before running the program, make sure you are in the virtual environment. Run `pipenv shell` to enter the virtual environment.

`main.py` is the entry point for this project. Run `python3 main.py -h` to see command line argument options for customization on the probing behaviors. To use all default options, you can run the program like this: `python3 main.py`

## 7. Program Walkthough

The program spins up a child process for `sniff-probes`, which runs constantly in the background to capture WiFi probe request.

Then, the program spawns another forever-running child process to collect data from the output of `sniff-probes` at a certain interval. Such interval is considered a monitoring session, the length of which is termed session duration. The rule for collecting probe requests in a single monitoring session is as follows:

1. Within one channel, only the timestamp of the first appearance of a MAC address is recorded. In other words, if the same MAC address is detected multiple times in a monitoring session, the timestamps from the second to last detection are discarded.
2. Within one channel, if the same MAC address appears multiple times, the rssi (i.e. WiFi signal strength) is averaged over all its appearances and rounded to integer.
3. If the same MAC address appears multiple times over different channels, the first appearance in each channel will be recorded. In other words, within one monitoring session, it is impossible to have multiple records of the same MAC address in one channel, but it is possible to have multiple records of the same MAC address over several channels.

The data collection process pipes in the output from the probing process, and preprocess the data into a `data_chunk` dictionary. When a monitoring session ends (i.e. SESS_DUR runs down to zero, but the probing process never stops), the data collection process pushes the `data_chunk` to a queue, which is connected to the parent process. It immediately resumes preprocessing data into the next `data_chunk` (i.e. monitoring session restarts).

In the parent process, meanwhile, a sqlite database and table will be created if it is not created already, accoding to the database location, table name, schema, and table creation query provided, and a connection object will be returned. If the database and table have been created already, the connection object is returned directly.

The parent process then reads the `data_chunk` from the queue and insert data into the table. The data insersion procedure is also running indefinitely.

## 7. TODO
* ~~Some of the configuration variables can be exposed as command line argument, specifically `SESS_DUR`.~~ (Implemented)
* ~~An automatic check can be added in a **separate bash script** to see whether WiFi chip monitor mode is set up,~~ and whether the correct WiFi interface is passed to `sniff-probes`.
* Test cases.
* ~~Error and info logging.~~ (Implemented)
* ~~Provide `debug=True` option.~~ (Not necessary, as all logging info is kept in `gatherer.log`)
* Create `Makefile` to enable command `make build`
