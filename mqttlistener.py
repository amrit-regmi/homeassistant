#!/usr/bin/env python3
import paho.mqtt.client as mqtt #import the client1
from rpi_rf import RFDevice
import time
import signal
import logging
import threading
import lirc
import timeit

irListening = False
upCode= 4483794
downCode= 4483796
stopCode= 4483800
rolling= "stopped"
finalPosition= 0.0
tempPosition = 0.0
maxPosition= 47
idealPosition= 45.2
rollUntilTime = 0.0
tracker = None
broadcaster = None 
refTime = None

rftxdevice = RFDevice(17)
rftxdevice.enable_tx() 


logging.basicConfig(level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S', format='%(asctime)-15s - [%(levelname)s] %(module)s: %(message)s',)

def isfloat(value):
  try:
    float(value)
    return True
  except ValueError:
    return False

def trackposition():

    global rollUntilTime,refTime,tempPosition,rftxdevice
    
    global rolling, finalPosition, idealposition,tracker

    #tracker = threading.currentThread()  
    
    while rolling != "stopped":
    
        
        print("Start Time => " + str(refTime))
        
        while time.time() <= rollUntilTime and rolling != "stopped":
            time.sleep(0.05)
            if rolling  == "down" and rolling != "stopped":
                tempPosition= finalPosition+ time.time() - refTime
                    
            if rolling == "up" and rolling != "stopped":
               
                tempPosition= finalPosition - time.time() + refTime
                    
            #print(str(rollUntilTime)+"     "+ str(time.time())+ "      --"+str( time.time() - refTime ) +" -   "+str(round(tempPosition,1)))
        
        else:
            rolling = "stopped"
            finalPosition = tempPosition
            if irListening:
                lirc.deinit()        
              
            rftxdevice.tx_code(stopCode, None, None)
            
    logging.info( "Rolling Stopped Current Position "+ str(round(finalPosition,1)) )
        
def callback_set_position(client, userdata, message):
    global rolling,tracker , finalPosition,rollUntilTime,tempPosition,broadcaster,rftxdevice,irListening
    global refTime
    
    code = message.payload.decode("utf-8")
    
    logging.info("Message received on topic HomeAssistant/positionScreen, payload: " +  str(code)) 
       
       
    if irListening:
        lirc.deinit()
        irListening = False
    
    finalPosition = tempPosition
    tempPosition = finalPosition
    
    if code == "pullDown": 
        logging.info("#########Pulling Down##########")
        rftxdevice.tx_code(downCode, None, None)
        rollUntilTime = time.time() + idealPosition- finalPosition
        rolling = "down"
        refTime = time.time()
        
        
    elif code == "pullUp":
        logging.info("#########Pulling Up##########")
        rftxdevice.tx_code(upCode, None, None)
        rollUntilTime =  time.time()+ finalPosition 
        rolling = "up"
        refTime = time.time()
        
        
        
    elif code == "stop":
        rftxdevice.tx_code(stopCode, None, None)
        rolling = "stopped"
        logging.info("#########Stopping########## Current Position " + str(tempPosition))
        #finalPosition = tempPosition
        
        
    elif isfloat(code):
        #logging.info("#########Setting to Position "+ str(code) +"##########")
        code= float(code)
        
        if code > finalPosition:
            if time.time() + code > time.time()+ maxPosition:
                logging.info("Screen cannot be rolled down to "+ str(code) + ". Rolling to maximum Position"+ str(maxPosition))
                code = maxPosition
            rftxdevice.tx_code(downCode, None, None)
            refTime = time.time()
            rollUntilTime =  time.time() + code - finalPosition
            rolling = "down"
            logging.info("#########Pulling Down##########")
        
            
        elif code < finalPosition:
            rftxdevice.tx_code(upCode, None, None)
            refTime = time.time()
            rolling = "up"
            logging.info("#########Pulling Up##########")
            rollUntilTime =  time.time()+ finalPosition- code
        else:
            logging.info("Invalid finalPositionreceived")
         
    else:
        logging.info("Received invalid code "+ code)
    
    
    if tracker == None or not tracker.isAlive():
       tracker = threading.Thread(target=trackposition)
       tracker.start()
        
    if broadcaster == None or not broadcaster.isAlive():    
       broadcaster = threading.Thread(target=publish_position)
       broadcaster.start()
       
    
def publish_position():
    global tempPosition,rolling,tracker
    broadcaster = threading.currentThread() 
    while tracker.isAlive():
        time.sleep(2)
        pos = round(tempPosition,1)
        logging.info("Broadcasting Position Update "+ str(pos))
        if tempPosition > 0.0:   
            client.publish("raspberryPiW/screenPosition",pos)
        elif tempPosition <= 0.0 or rolling == "stopped":
            client.publish("raspberryPiW/screenPosition",abs(pos))

def on_connect(client, userdata, flags, rc):
    if rc==0:
        client.connected_flag=True #set flag
        print("connected OK")
        r = client.subscribe("HomeAssistant/positionScreen")
        if r[0] == 0:
            logging.info("Subscribed to topic HomeAssistant/positionScreen")
        else:
            logging.info("Failed to subscribe, Error "+ str(r))
            
    else:
        logging.info("Bad connection Returned code=",rc)
        Client.bad_connection_flag = True

def listentoIR():
    global irListening
    sockid = lirc.init("myprogram")
    lirc.set_blocking(False,sockid)
    irListening = True
    while  True:
        try:
            list = lirc.nextcode()
            if len(list) != 0:
                logging.info("IR command "+ list[0]+ " Recevied ")
                client.publish("raspberryPiW/buttonpress",list[0])
                logging.info("Boardcasting remote button press"+ list[0] ) 
        except Exception as e:
                    time.sleep(1)
                    sockid = lirc.init("myprogram")
                    irListening = True
                    lirc.set_blocking(False,sockid)
                    logging.info("Exception raised "+ str(e) + ". Reintailizing")
        
    #irListening.join()
    #lirc.deinit()
    
mqtt.Client.connected_flag=False
mqtt.Client.bad_connection_flag=False 
broker="192.168.1.9"
client = mqtt.Client("python1")             #create new instance 
client.username_pw_set("mqttuser", "1991mpjg") #Username password
client.on_connect= on_connect  #bind call back function
client.message_callback_add("HomeAssistant/positionScreen", callback_set_position)
logging.info("Connecting to broker "+broker)
client.connect(broker)      #connect to broker

irlistener = threading.Thread(target=listentoIR)
irlistener.start()       

def startListningtoSignal():
        global rolling,tracker
        
        rfrxdevice = RFDevice(27)
        rfrxdevice.enable_rx()
        timestamp = None
        code = None
        #logging.info ("Listening for codes on GPIO " + str(27))
        while True:
            if rfrxdevice.rx_code_timestamp !=  timestamp:
                    if  rfrxdevice.rx_code != code:
                            code = rfrxdevice.rx_code
                            if code == upCode:
                                rolling = 'up'
                                #logging.info("###################REMOTE UP PRESSED######################")                            
                            elif code == downCode:
                                rolling = 'down'
                                #logging.info("###################REMOTE DOWN PRESSED######################")     
                            elif code == stopCode:
                                rolling = "stopped" 
                                #logging.info("###################REMOTE STOP PRESSED######################")     
                            timestamp = rfrxdevice.rx_code_timestamp
                            
                            #logging.info("################### "+ str(rfrxdevice.rx_code)+" ######################") 
                            ##logging.info(str(rfrxdevice.rx_code) + " [pulselength " + str(rfrxdevice.rx_pulselength) +", protocol " + str(rfrxdevice.rx_proto) + "]")
                        
                            if tracker == None or not tracker.isAlive():
                                tracker = threading.Thread(target=trackposition)
                                tracker.start()
                        
            time.sleep(0.01)
        rfrxdevice.cleanup() 
        

#startListningtoSignal
#irlistener.start()
client.loop_forever()
#time.sleep(60) 
#client.loop_stop()    #Stop loop 
#client.disconnect() # disconnect


