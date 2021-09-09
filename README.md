# Hausnet Heartbeat for Home Assistant

This Home Assistant component enables the Hausnet Heartbeat monitoring for 
a Home Assistant system. The Heartbeat service notifies the owner whenever
the HA system's heartbeat is not received on schedule.

Note that this component is in Beta, and has not yet been integrated with the main Home Assistant
distribution. Instead, it is installed and managed with the [Home Assistant Community Store](https://hacs.xyz/)
(HACS).

## Quick Start

First, at the [HausNet App site](https://app.hausnet.io):

1. Create an account.
2. Create a device (from the "Devices" menu) to represent your Home Assistant instance.
3. Copy your API access token from your profile.

Then, set up the component:

1. Install HACS following [these instructions](https://hacs.xyz/docs/installation/installation/)
2. Go to "HACS" on the left-side menu in Home Assistant.
3. Click on "Integrations"
4. Click on the three-dot item at the top right of the screen, and select "Custom Repositories"
5. Enter "https://github.com/HausNet/heartbeat-hass" in the "Add custom repository URL" field.
6. Select "Integration" in the "Category" select list.
7. Restart Home Assistant.
8. In your Home Assistant ```config/configuration.yml``` file, add the following section, using the token
   and device name from the service ("a6e24c2de1a23f21388028e18cc47bc5ca200b19" and "home" are just examples:
     ```
     # HausNet Heartbeat
     hausnet_heartbeat:
     api_key: "a6e24c2de1a23f21388028e18cc47bc5ca200b19"
     device: "home"
     ```
9. Restart Home Assistant. 

After the restart, your Home Assistant will start sending a heartbeat once every 15 minutes, and will let you know 
when it goes missing. You can monitor the log for any connection or authentic errors.

# Releases

## r0.1
Changed the hausmon service to "heartbeat", and added the latest heartbeat client as a dependency.

## r0.1.1
Changed the url of the service to "https://app.hausnet.io"
