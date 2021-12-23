#! /usr/bin/env python
#-*- coding: UTF-8 -*- 

from common.game_training import Game
import rospy
import DDPG
import TD3
import numpy as np

import visdom
import scipy.io as sio
import os
import threading

# hyper parameter
epsilon = 0.9
epsilon_decay = 0.99992

load_able = False # True if you want to load previous data

policy = "TD3" # DDPG or TD3
game_name = "empty_3m" # empty_?m / train_env_?m

# DDPG and TD3 params
state_dim = 39
action_dim = 2
hidden_dim = 500

discount = 0.99
actor_lr = 0.00001
critic_lr = 0.00001
tau = 0.01
buffer_size = 20000
batch_size = 512
alpha = 0.3
hyper_parameters_eps = 1.0

# td3 excluded
policy_noise =0.2
noise_clip = 0.5
policy_freq = 2

# game params
load_buffer_flag = False
load_actor_flag = False
load_critic_flag = False
fix_actor_flag = False

max_episode = 50

# variable
e = []
t = []
r = []
s = []
q = []
step_count_begin = 0
episode_begin = 0
agent = None

viz = visdom.Visdom(env="line")

# plot params
opts1={
    'showlegend': True,
    'title': "reward-episode",
    'xlabel': "episode",
    'ylabel': "reward",
}
opts2={
    'showlegend': True,
    'title': "reward-step",
    'xlabel': "step",
    'ylabel': "reward",
}
opts3={
    'showlegend': True,
    'title': "q_value-step",
    'xlabel': "step",
    'ylabel': "Q value",
}

# file url
data_url = os.path.dirname(os.path.realpath(__file__)) + '/data/' + policy + '/'

class myThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        # save data
        sio.savemat(data_url + 'step.mat',{'data': s},True,'5', False, False,'row')
        sio.savemat(data_url + 'reward.mat',{'data': r},True,'5', False, False,'row')
        sio.savemat(data_url + 'q_value.mat',{'data': q},True,'5', False, False,'row')
        sio.savemat(data_url + 'episode.mat',{'data': e},True,'5', False, False,'row')
        sio.savemat(data_url + 'total_reward.mat',{'data': t},True,'5', False, False,'row')
        sio.savemat(data_url + 'epsilon.mat',{'data': epsilon},True,'5', False, False,'row')

        # plot
        viz.line(t, e, win="gazebo1", name="line1", update=None, opts=opts1)
        viz.line(r, s, win="gazebo2", name="line2:", update=None, opts=opts2)
        viz.line(q, s, win="gazebo3", name="line3", update=None, opts=opts3)

        # save model
        agent.save(data_url + policy)

        rospy.loginfo("save temperory variables, plot, and save models.")

if __name__ == '__main__':

    # initialize ros
    rospy.init_node("training_node")

    # wait for world building
    rospy.sleep(rospy.Duration(3))

    # initialize environment
    env = Game("iris_0", game_name)

    # initialize agent

    kwargs = {
        'state_dim': state_dim,
        'action_dim': action_dim,
        'hidden_dim': hidden_dim,
        'discount': discount,
        'actor_lr': actor_lr,
        'critic_lr': critic_lr,
        'tau': tau,
        'buffer_size': buffer_size,
        'batch_size': batch_size,
        'alpha': alpha,
        'hyper_parameters_eps': hyper_parameters_eps,
        'policy_noise': policy_noise,
        'noise_clip': noise_clip,
        'policy_freq': 2,
        'load_buffer_flag': load_buffer_flag,
        'load_actor_flag': load_actor_flag,
        'load_critic_flag': load_critic_flag,
        'fix_actor_flag': fix_actor_flag
    }

    if (policy == "DDPG"):
        agent = DDPG.Agent(**kwargs)
    if (policy == "TD3"):
        agent = TD3.Agent(**kwargs)
    
    # create mat file
    if not os.path.exists(data_url + 'episode.mat'):
        os.system(r"touch {}".format(data_url + 'episode.mat'))
    if not os.path.exists(data_url + 'total_reward.mat'):
        os.system(r"touch {}".format(data_url + 'total_reward.mat'))
    if not os.path.exists(data_url + 'reward.mat'):
        os.system(r"touch {}".format(data_url + 'reward.mat'))
    if not os.path.exists(data_url + 'step.mat'):
        os.system(r"touch {}".format(data_url + 'step.mat'))
    if not os.path.exists(data_url + 'q_value.mat'):
        os.system(r"touch {}".format(data_url + 'q_value.mat'))
    if not os.path.exists(data_url + 'epsilon.mat'):
        os.system(r"touch {}".format(data_url + 'epsilon.mat'))

    # load data if true
    if load_able == True:

        e = list(sio.loadmat(data_url + 'episode.mat')['data'][0])
        t = list(sio.loadmat(data_url + 'total_reward.mat')['data'][0])
        r = list(sio.loadmat(data_url + 'reward.mat')['data'][0])
        s = list(sio.loadmat(data_url + 'step.mat')['data'][0])
        q = list(sio.loadmat(data_url + 'q_value.mat')['data'][0])
        epsilon = list(sio.loadmat(data_url + 'epsilon.mat')['data'][0])[0]

        print("restore epsilon:", epsilon)

        if len(r) > 0:
            step_count_begin = s[-1]
            print("restore step count:", step_count_begin)
        if len(e) > 0:
            episode_begin = e[-1] + 1
            print("restore episode:", episode_begin)

    # start to train
    for episode in range(episode_begin, 50):

        if episode == episode_begin:
            s0 = env.start()
            print("start!")
        else:
            s0 = env.reset()
            print("reset.")

        episode_reward = 0

        for step in range(300):

            step_count_begin += 1
            s.append(step_count_begin)

            a0 = agent.act(s0)

            print(a0)

            # E-greedy
            if epsilon > np.random.random():
                a0[0] = np.clip(a0[0] + np.random.random()*0.5, -1.0, 1.0)
                a0[1] = np.clip(a0[1] + np.random.random()*0.5, -1.0, 1.0)

            epsilon = max(epsilon_decay*epsilon, 0.10)
            
            print("eps = ", epsilon)

            begin_time = rospy.Time.now()

            s1, r1, done = env.step(0.1, (a0[0]+1)/4.0, 0, a0[1])
            q_value = agent.put(s0, a0, r1, s1, done)
            
            r.append(r1)
            q.append(q_value)

            episode_reward += r1
            s0 = s1

            agent.learn()

            if done:
                break

        print(episode, ': ', episode_reward)

        e.append(episode)
        t.append(episode_reward)

        myThread().start()

    rospy.spin()
