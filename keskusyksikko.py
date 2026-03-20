#!/usr/bin/env python3
"""
Program to take Artnet commands and pass them forward to a stepper motor.
Tuomas Valtonen / Akseli Konttas 2026
"""
import time
import pigpio
from python_artnet import python_artnet
import logging
from logging.handlers import RotatingFileHandler


## ============================

## ARTNET PARAMETERS

DMX_CHANNEL_DIRECTION   = 1     # Motor direction channel (low=clockwise, high=counter-clockwise)
DMX_CHANNEL_SPEED       = 2     # Motor speed channel (0=off, 255=max speed)

ARTNET_BIND_IP  = "0.0.0.0"
ARTNET_UNIVERSE = 15


## GPIO PARAMETERS

# Pin layout
ENABLE_PIN  = 5     # Motor enable pin; simply set to high
DIR_PIN     = 6     # Motor direction pin. Low=counter-clockwise, high=clockwise
SPEED_PIN   = 13    # Motor rotation speed (PWM). Higher PWM frequency -> faster rotation

# Maximum PWM frequency (MAX_FREQ -> max speed). Artnet value 255 (=max value) corresponds to this frequency. Modify this accordingly if needed
MAX_FREQ    = 12_800  # Hz


# Set up logging
rfh_debug = RotatingFileHandler("keskusyksikko_debug.log", encoding="utf-8", maxBytes=10*1024*1024, backupCount=3)  # Log file logging all events (including debug)
rfh_debug.setLevel(logging.DEBUG)
rfh = RotatingFileHandler("keskusyksikko.log", encoding="utf-8", maxBytes=10*1024*1024, backupCount=1)  # Log file logging all but debug events
rfh.setLevel(logging.INFO)
sh = logging.StreamHandler()
sh.setLevel(logging.WARNING)
logging.basicConfig(
    handlers=[ rfh, rfh_debug, sh ],
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.DEBUG
)

## ============================


def init_artnet(bind_ip, debug=False) -> python_artnet.Artnet:
    '''
    Initializes ArtNet connection.
    '''
    logging.debug(f"Starting to set up ArtNet... (bind ip: {bind_ip})")
    artnet = python_artnet.Artnet(ARTNET_BIND_IP, DEBUG=debug)
    logging.info(f"ArtNet ready. Bind ip '{bind_ip}', listening to universe {ARTNET_UNIVERSE}, direction DMX channel {DMX_CHANNEL_DIRECTION}, speed DMX channel {DMX_CHANNEL_SPEED}. ")
    return artnet


def init_gpio(dir_pin, speed_pin, enable_pin) -> pigpio.pi:
    '''
    Initializes pigpio.pi object and the necessary pins.
    '''
    logging.debug(f"Starting to setup PIGPIO... (direction pin: {dir_pin}, speed pin: {speed_pin}, enable pin: {enable_pin})")
    pi = pigpio.pi()

    # Set pin modes (all three pins as output)
    pi.set_mode(dir_pin,    pigpio.OUTPUT)
    pi.set_mode(speed_pin,  pigpio.OUTPUT)
    pi.set_mode(enable_pin, pigpio.OUTPUT)

    # Enable the motor (enable_pin to HIGH)
    pi.write(enable_pin, 1)

    logging.info(f"PIGPIO ready. Direction pin {dir_pin}, step pin {speed_pin}, enable pin {enable_pin}. Set enable pin to HIGH.")
    return pi


def dmx_value_to_pwm_frequency(dmx_val, max_pwm_freq=MAX_FREQ, max_value=255, stop_treshold=10) -> int:
    '''
    Maps DMX value in range [0, max_value] to PWM frequency in range [0, max_pwm_freq]:
        dmx_val <= stop_treshold  ---> returns 0
        dmx_val == max_value      ---> returns max_pwm_freq.
    '''
    freq = int(max_pwm_freq * (dmx_val-stop_treshold)/(max_value-stop_treshold))
    freq = max(0, freq)     # Set values under zero to zero
    return freq


def set_motor_speed(pi: pigpio.pi, speed: int, clockwise: bool=True, dir_pin=DIR_PIN, speed_pin=SPEED_PIN, max_pwm_freq=MAX_FREQ):
    '''
    Set the motor to rotate with a certain speed and direction.
    @param speed: Int in range [0,255], where 255 is maximum speed and 0 stops the motor.
    @param clockwise: True for clockwise rotation, False for counter-clockwise
    @param dir_pin: GPIO pin for motor direction
    @para
    '''
    stop_treshold   = 10                        # Speed this or less -> considered as 0 -> stop the motor
    pwm_duty        = 500_000                   # 0 off, 1M fully on -> 500K is 50/50
    freq            = dmx_value_to_pwm_frequency(speed, max_pwm_freq, stop_treshold=stop_treshold)
    direction       = 1 if clockwise else 0     # Direction pin high (1) if clockwise, low (0) if counter-clockwise

    # Set the direction as needed
    pi.write(dir_pin, direction)

    # Set PWM according to the calculated frequency (force the frequency to be an integer)
    pi.hardware_PWM(speed_pin, freq, pwm_duty)
    
    logging.debug(f"PWM on pin {speed_pin}: PWM frequency {freq} Hz, PWM duty cycle {pwm_duty}. Dir pin {dir_pin}, set to {direction}")


def main():
    logging.info("Starting the application")
    print("Keskusyksikko v1.0.0 käynnistyy...")

    try:
        # Initialize ArtNet
        artnet  = init_artnet(ARTNET_BIND_IP, debug=False)

        # Initialize gpio
        pi      = init_gpio(DIR_PIN, SPEED_PIN, ENABLE_PIN)


        # Loop until exit :)
        while True:
            time.sleep(0.01)
            
            # Fetch last ArtNet package
            artnet_buffer = artnet.readBuffer()

            # Did we get a buffer?
            if artnet_buffer is None: continue
            
            artnet_packet = artnet_buffer[ARTNET_UNIVERSE]

            # Did we get a package?
            if artnet_packet is None: continue

            dmx_packet = artnet_packet.data

            # Is there any data?
            if dmx_packet is None: continue

            # Direction and speed from the dmx package
            clockwise = True    # Values 0-127 for clockwise rotation; 128-255 counter-clockwise
            if int(dmx_packet[DMX_CHANNEL_DIRECTION-1]) <= 127:
                clockwise = False
            speed = int(dmx_packet[DMX_CHANNEL_SPEED-1])
            logging.debug(f"DMX channel {DMX_CHANNEL_SPEED}={speed}, channel {DMX_CHANNEL_DIRECTION}={int(dmx_packet[DMX_CHANNEL_DIRECTION-1])}")
            
            # Set the speed and direction
            set_motor_speed( pi, speed, clockwise=clockwise )

            
    except KeyboardInterrupt:
        logging.info("Stopping execution.")
        print("Keskusyksikkö sammuu.")

    except:
        logging.exception('Got an exception')
        logging.critical("Aborting execution.")
        print("Keskusyksikkö kaatui :(")

    finally:
        try:    artnet.close()
        except: logging.exception('Got an exception when closing Artnet')
        try:    set_motor_speed(pi, 0)
        except: logging.exception('Got an exception when stopping the motor')
        logging.info("Exiting the application.")


if __name__ == "__main__":
    main()
