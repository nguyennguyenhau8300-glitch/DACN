// ESP32 reference firmware; not yet validated on a physical board.
// Libraries: PubSubClient, ArduinoJson. Echo input must be 3.3V compatible.
// Configure broker TLS/accounts/ACL before using outside the local simulator.
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include "secrets.h"

WiFiClient transport;
PubSubClient mqtt(transport);
Preferences state;
const int TRIG=5,ECHO=18;
String pending;
uint64_t sequence=0;
unsigned long lastSend=0;

void received(char *topic, byte *payload, unsigned int length){
  JsonDocument ack;
  if(deserializeJson(ack,payload,length))return;
  if(ack["device_code"].as<String>()==DEVICE_CODE && ack["sequence"].as<uint64_t>()==sequence)pending="";
}

void setup(){
  pinMode(TRIG,OUTPUT);pinMode(ECHO,INPUT);
  state.begin("parkly",false);sequence=state.getULong64("seq",0);
  WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
  mqtt.setServer(MQTT_HOST,1883);mqtt.setCallback(received);mqtt.setBufferSize(1024);
}

void loop(){
  if(WiFi.status()!=WL_CONNECTED){delay(500);return;}
  if(!mqtt.connected()){
    if(!mqtt.connect(DEVICE_CODE,MQTT_USER,MQTT_PASSWORD)){delay(2000);return;}
    mqtt.subscribe((String("parkly/devices/")+DEVICE_CODE+"/ack").c_str(),1);
  }
  mqtt.loop();
  if(millis()-lastSend<5000)return;
  lastSend=millis();
  if(pending.length()==0){
    digitalWrite(TRIG,LOW);delayMicroseconds(2);digitalWrite(TRIG,HIGH);delayMicroseconds(10);digitalWrite(TRIG,LOW);
    unsigned long duration=pulseIn(ECHO,HIGH,30000);
    if(!duration)return; // Missing measurement does not mean an empty spot.
    float distance=duration*.0343f/2;
    sequence++;state.putULong64("seq",sequence); // Persist before sending; do not reuse a sequence after reboot.
    JsonDocument data;
    data["api_key"]=DEVICE_API_KEY;
    data["telemetry"]["sequence"]=sequence;
    data["telemetry"]["sensor_status"]=distance<80?"OCCUPIED":"AVAILABLE";
    serializeJson(data,pending);
  }
  mqtt.publish((String("parkly/devices/")+DEVICE_CODE+"/telemetry").c_str(),pending.c_str(),false);
  // QoS0 publisher retries identical payload until the backend ACK is received.
}
