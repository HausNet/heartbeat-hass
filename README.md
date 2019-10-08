# hausmon-hass

HausMon Client integration into Home Assistant. The HausMon service
is a simple Dead Man's Switch to send alerts when a home automation
network does not regularly reset it. This way you'll know when 
something went wrong even when the network cannot be reached. This 
module integrates the HausMon API Client into the Home Assistant 
(HASS) environment.

## Quick Start

1. Check out this repository into your HASS config/hausmon directory: 
   ```shell script
   cd [hass-install-directory]/config
   git clone git@github.com:liber-tas/hausmon-hass.git hausmon
   ```
1. Create an account at the [HausNet website](http://hausnet.io).
1. From the website, get your API key.
1. Open your HASS config file, and enter the following YAML:
   ```yaml
   hausmon:
       api_endpoint: "http://mon.hausnet.io/api"
       api_key: "[Your API key from hausnet.io]"
   ```
1. Restart and you're set! The client will now send a timer reset
   request to the service every 15 minutes, and the service will 
   report to you when it doe 
