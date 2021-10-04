#! /usr/bin/env python
#-*- coding: UTF-8 -*- 

import game
import rospy
import numpy as np
from ddpg_PER import Agent
import visdom
import scipy.io as sio
import os

# hyper parameter
epsilon = 0.9
epsilon_decay = 0.99995

x = []
y = []
r = []
s = []
q = []
step_count_begin = 0
episode_begin = 0
agent = None
load_able = True # True if you want to load previous data

params = {
        'gamma': 0.90,
        'actor_lr': 0.0001,
        'critic_lr': 0.0001,
        'tau': 0.01,
        'buffer_size': 100000,
        'batch_size': 512,
        'alpha': 0.3,
        'hyper_parameters_eps': 0.2,
        'load_data': True
}

viz = visdom.Visdom(env="line")

# tool function

def limit(x, max_x, min_x):
    return max(min(x, max_x), min_x)

if __name__ == '__main__':
    rospy.init_node("test")
    # global env
    env = game.Game("iris_0")
    
    # load data
    if load_able == True:
        # x = list(sio.loadmat(os.path.dirname(os.path.realpath(__file__)) + '/episode.mat')['data'])[0]
        x = list(sio.loadmat(os.path.dirname(os.path.realpath(__file__)) + '/episode.mat')['data'][0])
        y = list(sio.loadmat(os.path.dirname(os.path.realpath(__file__)) + '/total_reward.mat')['data'][0])
        r = list(sio.loadmat(os.path.dirname(os.path.realpath(__file__)) + '/reward.mat')['data'][0])
        s = list(sio.loadmat(os.path.dirname(os.path.realpath(__file__)) + '/step.mat')['data'][0])
        q = list(sio.loadmat(os.path.dirname(os.path.realpath(__file__)) + '/q_value.mat')['data'][0])
        epsilon = list(sio.loadmat(os.path.dirname(os.path.realpath(__file__)) + '/epsilon.mat')['data'][0])[0]
        print("restore epsilon:", epsilon)

        if len(r) > 0:
            step_count_begin = s[-1]
            print("restore step count:", step_count_begin)
        if len(x) > 0:
            episode_begin = x[-1] + 1
            print("restore episode:", episode_begin)


    # plotTimer = rospy.Timer(rospy.Duration(60), plotCB)

    agent = Agent(**params)

    for episode in range(episode_begin, 1000):
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

            # E-greedy
            if epsilon > np.random.random():
                a0[0] += np.random.random()*0.4
                a0[1] += (np.random.random()-0.5)*0.4

                a0[0] = limit(a0[0], 1.0, 0.0)
                a0[1] = limit(a0[1], 1.0, -1.0)

            epsilon = max(epsilon_decay*epsilon, 0.10)
            
            print("eps = ", epsilon)

            begin_time = rospy.Time.now()
            s1, r1, done = env.step(0.1, a0[0], 0, a0[1])
            q_value = agent.put(s0, a0, r1, s1, done)
            
            r.append(r1)
            q.append(q_value)

            end_time = rospy.Time.now()

            episode_reward += r1
            s0 = s1

            begin_time = rospy.Time.now()
            agent.learn()
            end_time = rospy.Time.now()

            if done:
                break

        print(episode, ': ', episode_reward)

        x.append(episode)
        y.append(episode_reward)

        sio.savemat(os.path.dirname(os.path.realpath(__file__)) + '/step.mat',{'data': s},True,'5', False, False,'row')
        sio.savemat(os.path.dirname(os.path.realpath(__file__)) + '/reward.mat',{'data': r},True,'5', False, False,'row')
        sio.savemat(os.path.dirname(os.path.realpath(__file__)) + '/q_value.mat',{'data': q},True,'5', False, False,'row')
        sio.savemat(os.path.dirname(os.path.realpath(__file__)) + '/episode.mat',{'data': x},True,'5', False, False,'row')
        sio.savemat(os.path.dirname(os.path.realpath(__file__)) + '/total_reward.mat',{'data': y},True,'5', False, False,'row')
        sio.savemat(os.path.dirname(os.path.realpath(__file__)) + '/epsilon.mat',{'data': epsilon},True,'5', False, False,'row')

        # plot
        viz.line(
            y,
            x,
            win="gazebo1",
            name="line1",
            update=None,
            opts={
                'showlegend': True,
                'title': "reward-episode",
                'xlabel': "episode",
                'ylabel': "reward",
            },
        )
        viz.line(
            r,
            s,
            win="gazebo2",
            name="line2",
            update=None,
            opts={
                'showlegend': True,
                'title': "reward-step",
                'xlabel': "step",
                'ylabel': "reward",
            },
        )
        viz.line(
            q,
            s,
            win="gazebo3",
            name="line3",
            update=None,
            opts={
                'showlegend': True,
                'title': "q_value-step",
                'xlabel': "step",
                'ylabel': "Q value",
            },
        )

        # save model
        agent.save_data()

    rospy.spin()

        


