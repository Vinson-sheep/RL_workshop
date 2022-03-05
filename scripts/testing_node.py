#! /usr/bin/env python
#-*- coding: UTF-8 -*- 

from common.game_testing import Game
from mavros_msgs.msg import PositionTarget
import rospy
import DDPG
import TD3
import numpy as np
import os
import pickle
from multi_rotor_avoidance_rl.msg import State

# hyper parameter
max_testing_num = 100

restore_able = False

policy = "TD3" # DDPG or TD3
filter = "MAF" # NONE / FIR / MAF / FOLF
game_name = "train_env_7m"
recover_mode = False

# Median Average Filter
window_size = 8
# First-Order Lag Filter
action_discount = 0.2

# recover_mode
recover_time = 1.5
recover_limit = 0.3
deltaT = 0.4

# DDPG and TD3 params
state_dim = 41
action_dim = 2
# hidden_dim = 500
hidden_dim = 300

# variable
testing_num_begin = 0
cur_testing_num = 0
cur_success_num = 0
cur_crash_num = 0
recovery_num = 0

# file url
data_url = os.path.dirname(os.path.realpath(__file__)) + '/data/' + policy + '/'

step_time = 0.05

def save():

    save_file = open(data_url + 'temp_test.bin',"wb")
    pickle.dump(cur_testing_num,save_file)
    pickle.dump(cur_success_num,save_file)
    pickle.dump(cur_crash_num, save_file)
    pickle.dump(recovery_num, save_file)

    print("store cur_testing_num: ", cur_testing_num, "cur_success_num: ", cur_success_num, 
        "cur_crash_num: ", cur_crash_num, "recovery_num", recovery_num)

    save_file.close()
    

def load():

    load_file = open(data_url + 'temp_test.bin',"rb")
    cur_testing_num=pickle.load(load_file)
    cur_success_num=pickle.load(load_file)
    cur_crash_num = pickle.load(load_file)
    recovery_num = pickle.load(load_file)

    print("restore cur_testing_num: ", cur_testing_num, "cur_success_num: ", cur_success_num, 
        "cur_crash_num: ", cur_crash_num, "recovery_num", recovery_num)

    return cur_testing_num, cur_success_num, cur_crash_num, recovery_num

if __name__ == '__main__':

    # initialize ros
    rospy.init_node("testing_node")

    # raw data
    rawCmdPub = rospy.Publisher("raw_cmd", PositionTarget, queue_size=1)
    modCmdPub = rospy.Publisher("mod_cmd", PositionTarget, queue_size=1)
    statePub = rospy.Publisher("state", State, queue_size=1)

    # wait for world building
    rospy.sleep(rospy.Duration(3))
    
    # initialize environment
    env = Game("iris", game_name)

    # initialize agent

    kwargs = {
        'state_dim': state_dim,
        'action_dim': action_dim,
        'hidden_dim': hidden_dim,
        'discount': 0,
        'actor_lr': 0,
        'critic_lr': 0,
        'tau': 0,
        'buffer_size': 0,
        'batch_size': 0,
        'alpha': 0,
        'hyper_parameters_eps': 0,
        'policy_noise': 0,
        'noise_clip': 0,
        'policy_freq': 0,
        'load_buffer_flag': False,
        'load_actor_flag': True,
        'load_critic_flag': False,
        'load_optim_flag': False,
        'fix_actor_flag': True,
        'policy': policy
    }

    if (policy == "DDPG"):
        agent = DDPG.Agent(**kwargs)
    if (policy == "TD3"):
        agent = TD3.Agent(**kwargs)

    # load data if true
    if restore_able == True:
        cur_testing_num, cur_success_num, cur_crash_num, recovery_num = load()

    cur_testing_num += 1
    testing_num_begin = cur_testing_num

    # start to test
    for episode in range(testing_num_begin, max_testing_num+1):

        cur_testing_num = episode

        if episode == testing_num_begin:
            s0 = env.start()
            print("start testing！")
        else:
            s0 = env.reset()
            print("restore testing.")

        recovery_flag = False

        # no filter
        if (filter == "NONE"):

            for step in range(1000):

                begin_time = rospy.Time.now()

                # DEBUG
                msg = State()
                msg.header.stamp = rospy.Time.now()
                msg.data = s0
                statePub.publish(msg)

                a0 = agent.act(s0)

                # DEBUG
                pt = PositionTarget()
                pt.velocity.x = (a0[0]+1)/4.0
                pt.yaw_rate = a0[1]
                rawCmdPub.publish(pt)

                # DEBUG
                modCmdPub.publish(pt)

                # recovery check
                valid_flag, _ = env.is_valid(s0, [pt.velocity.x, pt.yaw_rate], time_step=deltaT, limit=recover_limit)

                if recover_mode and not valid_flag:
                    recovery_flag = True
                    if env.recovery(time=recover_time): # if crash when recovering
                        cur_crash_num += 1
                        print("recover but crash!")
                        break

                    s0 = env.cur_state()
                    continue

                # step
                s1, _, done = env.step(step_time, pt.velocity.x, 0, pt.yaw_rate)
        
                s0 = s1

                # check result
                crash_indicator, _, _ = env.is_crashed()
                arrive_indicator = env.is_arrived()


                if done == True:
                    if crash_indicator == True:
                        cur_crash_num += 1
                        print("crashed!")
                    elif arrive_indicator == True:
                        cur_success_num += 1
                        print("arrived")
                    break

                rospy.sleep(rospy.Duration(step_time)-(rospy.Time.now() - begin_time))


        # Median Average Filter
        if (filter == "MAF"):
            
            window_vx = [0.0]*window_size
            window_vyaw = [0.0]*window_size

            for step in range(1000):

                begin_time = rospy.Time.now()
                
                # DEBUG
                msg = State()
                msg.header.stamp = rospy.Time.now()
                msg.data = s0
                statePub.publish(msg)

                a0 = agent.act(s0)

                # DEBUG
                pt = PositionTarget()
                pt.velocity.x = (a0[0]+1)/4.0
                pt.yaw_rate = a0[1]
                rawCmdPub.publish(pt)

                # update queue
                window_vx.pop(0)
                window_vx.append(a0[0])
                window_vyaw.pop(0)
                window_vyaw.append(a0[1])

                # copy data and sort
                window_vyaw_copy = window_vyaw[:]
                window_vyaw_copy.sort()
                window_vx_copy = window_vx[:]
                window_vx_copy.sort()

                # DEBUG
                pt.velocity.x = (np.mean(window_vx_copy[1:-1])+1)/4.0
                pt.yaw_rate = np.mean(window_vyaw_copy[1:-1])
                modCmdPub.publish(pt)

                # recovery check
                valid_flag, _ = env.is_valid(s0, [pt.velocity.x, pt.yaw_rate], time_step=deltaT, limit=recover_limit)

                if recover_mode and not valid_flag:
                    recovery_flag = True
                    if env.recovery(time=recover_time): # if crash when recovering
                        cur_crash_num += 1
                        print("recover but crash!")
                        break

                    s0 = env.cur_state()
                    continue
                    

                # step
                s1, _, done = env.step(step_time, pt.velocity.x, 0, pt.yaw_rate)
                
                s0 = s1

                # check result
                crash_indicator, _, _ = env.is_crashed()
                arrive_indicator = env.is_arrived()

                if done == True:
                    if crash_indicator == True:
                        cur_crash_num += 1
                        print("crashed!")
                    elif arrive_indicator == True:
                        cur_success_num += 1
                        print("arrived")
                    break

                rospy.sleep(rospy.Duration(step_time)-(rospy.Time.now() - begin_time))

        # First-Order Lag Filter
        if (filter == "FOLF"):

            momentum = [0.0]*action_dim

            for step in range(1000):

                begin_time = rospy.Time.now()
                
                # DEBUG
                msg = State()
                msg.header.stamp = rospy.Time.now()
                msg.data = s0
                statePub.publish(msg)

                a0 = agent.act(s0)

                # DEBUG
                pt = PositionTarget()
                pt.velocity.x = (a0[0]+1)/4.0
                pt.yaw_rate = a0[1]
                rawCmdPub.publish(pt)

                momentum[0] = (1-action_discount)*momentum[0] + action_discount*a0[0]
                momentum[1] = (1-action_discount)*momentum[1] + action_discount*a0[1]

                # DEBUG
                pt.velocity.x = (momentum[0]+1)/4.0
                pt.yaw_rate = momentum[1]
                modCmdPub.publish(pt)

                # recovery check
                valid_flag, _ = env.is_valid(s0, [pt.velocity.x, pt.yaw_rate], time_step=deltaT, limit=recover_limit)

                if recover_mode and not valid_flag:
                    recovery_flag = True
                    if env.recovery(time=recover_time): # if crash when recovering
                        cur_crash_num += 1
                        print("recover but crash!")
                        break

                    s0 = env.cur_state()
                    continue

                # step
                s1, _, done = env.step(step_time, pt.velocity.x, 0, pt.yaw_rate)
                
                s0 = s1

                # check result
                crash_indicator, _, _ = env.is_crashed()
                arrive_indicator = env.is_arrived()

                if done == True:
                    if crash_indicator == True:
                        cur_crash_num += 1
                        print("crashed!")
                    elif arrive_indicator == True:
                        cur_success_num += 1
                        print("arrived")
                    break

                rospy.sleep(rospy.Duration(step_time)-(rospy.Time.now() - begin_time))
            
        
        if recovery_flag:
            recovery_num +=1

        print('[' + str(episode) + ']', ' success_num', cur_success_num, ' crash_num', cur_crash_num, ' recovery_num', recovery_num)

        save()


    rospy.spin()

        


