# Configuration

`http2mqtt.py` reads a yaml file with its configuration.

The file allows the options as described in the following sections.

## General options

    loglevel: debug|info|warning|error|critical

configures the loglevel. If omitted it defaults to `warning`.

## MQTT options

    mqtt:
      hostname: "192.168.0.2"
      port: 1883
      user: username
      password: password
      identifier: identifier

The hostname of the mqtt broker needs to be configured.
All other options are optional.

## HTTP options

### Polling

    http:
      - url: "http://192.168.0.15/"
        error_topic: "smartWb/httpErrors"
        requests:
          - endpoint: getParameters
            cycle: 10
            method: "GET"
            topics:
              - topic: "smartWb/meterReading"
                json_path: "$.list.[0].meterReading"
              - topic: "smartWb/status"
                json_path: "$.list.[0].vehicleState"
                map:
                  1: A
                  2: B
                  3: C

This configures a HTTP server for which the endpoint `getParameters` is called every 10 seconds (`cycle`).
The method is `GET` as default, but any other HTTP method can be configured.

If the HTTP request is not successful (i.e. timeout), the error counter for this endpoint is increased by 1 and published with via MQTT with the `error_topic` topic.
If `error_topic` is not configured, no MQTT topic is published, but the problem is still logged to STDOUT.

When the HTTP request is successful, the information defined by `json_path` will be extracted from the response and sent as MQTT topic as defined.
Before sending the value, a mapping can be applied.

If the mapping is configured, the MQTT topic will only be sent, if the value is found in the map.
Otherwise it will be dropped silently.

This can be changed by configuring a `map_default`:

    map:
      0: 'false'
    map_default: 'true'

In this case the value specified as `map_default` will be sent when it is not found in the map.
`map_default: '{value}'` will send the raw value when no suitable mapping is found in the map.

### Triggers

    - url: "http://192.168.0.15/"
      error_topic: "smartWb/httpErrors"
      requests:
        - &getParameters
          endpoint: getParameters
          cycle: 10
          topics:
            - topic: "smartWb/meterReading"
              json_path: "$.list.[0].meterReading"
            - topic: "smartWb/actualPower"
              json_path: "$.list.[0].actualPower"
            - topic: "smartWb/actualCurrent"
              json_path: "$.list.[0].actualCurrent"
            - topic: "smartWb/vehicleState"
              json_path: "$.list.[0].vehicleState"
            - topic: "smartWb/evseState"
              json_path: "$.list.[0].evseState"
            - topic: "smartWb/status"
              json_path: "$.list.[0].vehicleState"
              map:
                1: A
                2: B
                3: C
      triggers:
        - topic: "smartWb/setCurrent"
          requests: 
            - endpoint: setCurrent
              params:
                current: "{payload}"
              method: "GET"
            - <<: *getParameters

For every URL also trigges can be configured.
When a message with the given MQTT topic is received, every endpoint specified under `requests` is requested (in the given order).
The payload from the MQTT topic can be included into the HTTP request params.

The example above uses YAML anchors and aliases to avoid repeating the configuration of the `getParameters` endpoint.

