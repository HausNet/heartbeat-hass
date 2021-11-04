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

1. If not installed yet, install HACS following [these instructions](https://hacs.xyz/docs/installation/installation/).
2. After restarting, go to "HACS" on the left-side menu in Home Assistant.
3. Click on "Integrations".
4. Click on the three-dot item at the top right of the screen, and select "Custom Repositories".
5. Enter "https://github.com/HausNet/heartbeat-hass" in the "Add custom repository URL" field.
6. Select "Integration" in the "Category" select list and click "Add", then close the window.
7. Then, click the "Explore & Add Repositories" button at bottom right.
8. Find the "HausNet Heartbeat" repository, click on it, and in the new window that opens up, click "Install this repository in HACS".
9. Confirm the installation in the subsequent window by clicking "Install" - you'll see the component in the main Home Assistant window with a "Pending Restart" notice on it.
10. Restart Home Assistant.

Now that the integration has been made available in HACS, we need to install it in Home Assistant:

1. Go to "Configuration" on the side menu, and click the "Add Integration" button at bottom right.
2. In the pop-up window, search for the "HausNet Heartbeat" integration, and click on it when found.
3. A configuration pop-up will appear - enter the Heartbeat API token, and the device name you defined at the service, and submit.

Your Home Assistant will now start sending a heartbeat once every 15 minutes, and the service will let you know 
when it goes missing. You can monitor the log for any connection or authentication errors.

# Releases

## r0.2.1
- Fixed HACS integration defects
- Fixed heartbeat recognition defects
- Updated info.md to be a copy of README.md

## r0.2
- Integrated the (thin) client into the component.
- Moved configuration to the UI from YAML.

## r0.1
Changed the hausmon service to "heartbeat", and added the latest heartbeat client as a dependency.

## r0.1.1
Changed the url of the service to "https://app.hausnet.io"

## r0.2
Integrated the client into the component.
Changed from YAML configuration to config entries on the UI>
