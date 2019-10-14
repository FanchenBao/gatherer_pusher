#!/bin/bash

# channel hop every 0.5 seconds
channel_hop() {
  IEEE80211bg="1 2 3 4 5 6 7 8 9 10 11"
  IEEE80211bg_intl="$IEEE80211b 12 13 14"
  IEEE80211a="36 40 44 48 52 56 60 64 149 153 157 161"
  IEEE80211bga="$IEEE80211bg $IEEE80211a"
  IEEE80211bga_intl="$IEEE80211bg_intl $IEEE80211a"

  while true ; do
    for CHAN in $IEEE80211bg ; do
      echo $CHAN
      # echo "switching $IFACE to channel $CHAN"
      sudo iwconfig $IFACE channel $CHAN
      sleep $CHANNEL_DUR
    done
  done
}

main() {
  if [[ $IFACE == "" ]]; then
      echo "WiFi interface env variable must be set in [-i wifi_interface]. Type \"ifconfig\" to view network interaces."
      exit 1
  fi

  if [[ $CHANNEL_HOP == "true" ]]; then
      # channel hop in the background
      channel_hop &
      CH_PID=$!
  fi

  # No filtering for the output
  if [[ $OUTPUT == "" ]]; then
    sudo tcpdump -tttt -l -I -i "$IFACE" -e -s 256 type mgt subtype probe-req
  else  # only produce output file if user explicitly specifies so.
    sudo tcpdump -tttt -l -I -i "$IFACE" -e -s 256 type mgt subtype probe-req | tee -a "$OUTPUT"
  fi
}

cleanup() {
    if ps -p $CH_PID > /dev/null; then  # check if the process is still running
        kill $CH_PID
    fi
}



# DEFAULTS
CHANNEL_HOP="false"
OUTPUT=""
IFACE=""
CHANNEL_DUR="0.5"

print_usage() {
  printf "%s\n" "Usage: sniff-probes.sh [--channel_hop] [-i wifi_interface] [-o output_file] [-d channel_duration]"
  printf "%s\t%s\n" "--channel_hop" "Enable channel hop while monitoring. Default: false"
  printf "%s\t\t%s\n" "-i" "WiFi device interface in monitor mode. Required." \
    "-o" "Output file name. Default: no file output" \
    "-d" "Time to spend on each channel in channel hop, in seconds. Default: 0.5"
}

# Parse options and flags
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --channel_hop)  # enable channel hop
      CHANNEL_HOP="true"
      shift 1
      ;;
    -i)  # wifi device interface that is in monitor mode
      if [[ "$2" != "" ]]; then
        IFACE="$2"
        shift 1
      else # -i must be followed by a second argument
        print_usage
        exit 1
      fi
      shift 1
      ;;
    -o)  # output file name
      if [[ "$2" != "" ]]; then
        OUTPUT="$2"
        shift 1
      else # -o must be followed by a second argument
        print_usage
        exit 1
      fi
      shift 1
      ;;
    -d)  # time to spend on each channel in channel hop
      if [[ "$2" =~ ^[0-9]+\.?[0-9]*$ ]]; then
        CHANNEL_DUR="$2"
        shift 1
      else # -d must be followed by a valid numeric value
        print_usage
        exit 1
      fi
      shift 1
      ;;
    *) # unsupported flags
      print_usage
      exit 1
      ;;
  esac
done

# clean up after exit
trap cleanup EXIT

main