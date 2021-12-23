#! /usr/bin/env python
# coding :utf-8

import math
import random
import numpy as np

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from common.prioritized_replay_buffer import PrioritizedReplayBuffer
import os
import copy

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

class Actor(nn.Module):

    def __init__(self, state_dim, hidden_dim, action_dim):
        super(Actor, self).__init__()
        self.l1 = nn.Linear(state_dim, hidden_dim)
        self.l2 = nn.Linear(hidden_dim, hidden_dim)
        self.l3 = nn.Linear(hidden_dim, hidden_dim)
        self.l4 = nn.Linear(hidden_dim, action_dim)
        
    def forward(self, state):
        a = torch.relu(self.l1(state))
        a = torch.relu(self.l2(a))
        a = torch.relu(self.l3(a))
        a = torch.tanh(self.l4(a))
        
        return a


class Critic(nn.Module):

    def __init__(self, state_dim, hidden_dim, action_dim):
        super(Critic, self).__init__()

        # Q1 architecture
        self.l1 = nn.Linear(state_dim+action_dim, hidden_dim)
        self.l2 = nn.Linear(hidden_dim, hidden_dim)
        self.l3 = nn.Linear(hidden_dim, hidden_dim)
        self.l4 = nn.Linear(hidden_dim, 1)

        # Q2 architecture
        self.l5 = nn.Linear(state_dim+action_dim, hidden_dim)
        self.l6 = nn.Linear(hidden_dim, hidden_dim)
        self.l7 = nn.Linear(hidden_dim, hidden_dim)
        self.l8 = nn.Linear(hidden_dim, 1)


    def forward(self, state, action):
        sa = torch.cat([state, action], 1)

        q1 = torch.relu(self.l1(sa))
        q1 = torch.relu(self.l2(q1))
        q1 = torch.relu(self.l3(q1))
        q1 = self.l4(q1)

        q2 = torch.relu(self.l5(sa))
        q2 = torch.relu(self.l6(q2))
        q2 = torch.relu(self.l7(q2))
        q2 = self.l8(q2)

        return q1, q2

    def Q1(self, state, action):
        sa = torch.cat([state, action], 1)
        
        q1 = torch.relu(self.l1(sa))
        q1 = torch.relu(self.l2(q1))
        q1 = torch.relu(self.l3(q1))
        q1 = self.l4(q1)

        return q1


class Agent(object):

    def __init__(self, **kwargs):

        # load params
        for key, value in kwargs.items():
            setattr(self, key, value)

        # initialize net
        self.actor = Actor(self.state_dim, self.hidden_dim, self.action_dim).to(device)
        self.actor_target = copy.deepcopy(self.actor)
        self.actor_optimizer = optim.Adam(self.actor.parameters(), lr = self.actor_lr)

        self.critic = Critic(self.state_dim, self.hidden_dim, self.action_dim).to(device)
        self.critic_target = copy.deepcopy(self.critic)
        self.critic_optimizer = optim.Adam(self.critic.parameters(), lr = self.critic_lr)

        self.buffer = PrioritizedReplayBuffer(self.buffer_size, self.batch_size)

        self.load(os.path.dirname(os.path.realpath(__file__)) + '/data/TD3/TD3')

        self.total_it = 0

        
    def act(self, state):
        state = torch.FloatTensor(state.reshape(1, -1)).to(device)
        return self.actor(state).cpu().data.numpy().flatten()
    

    def put(self, *transition): 
        """
        return Q_value of state, action
        """

        state, action, reward, next_state, done = transition

        state = torch.FloatTensor(state).to(device).unsqueeze(0)
        action = torch.FloatTensor(action).to(device).unsqueeze(0)

        Q = self.critic.Q1(state, action).detach()

        self.buffer.add(transition, 10000.0)

        return Q.cpu().item()


    def learn(self):
        
        self.total_it += 1

        if not self.buffer.sample_available():
            return

        # Sample replay buffer 

        samples, indices = self.buffer.sample()

        state, action, reward, next_state, done = zip(*samples)

        state = torch.tensor(state, dtype=torch.float).to(device)
        action = torch.tensor(action, dtype=torch.float).to(device)
        reward = torch.tensor(reward, dtype=torch.float).view(self.batch_size,-1).to(device)
        next_state = torch.tensor(next_state, dtype=torch.float).to(device)
        done = torch.tensor(done, dtype=torch.float).to(device).view(self.batch_size,-1).to(device)

        with torch.no_grad():
            # Select action according to policy and add clipped noise
            noise = (
				torch.randn_like(action) * self.policy_noise
			).clamp(-self.noise_clip, self.noise_clip)

            next_action = (
				self.actor_target(next_state) + noise
			).clamp(-1, 1)

            # Compute the target Q value
            target_Q1, target_Q2 = self.critic_target(next_state, next_action)
            target_Q = torch.min(target_Q1, target_Q2)
            target_Q = reward + (1-done) * self.discount * target_Q

        # Get current Q estimates
        current_Q1, current_Q2 = self.critic(state, action)

        # Compute critic loss
        critic_loss = F.mse_loss(current_Q1, target_Q) + F.mse_loss(current_Q2, target_Q)

        # Optimize the critic
        self.critic_optimizer.zero_grad()
        critic_loss.backward()
        print("critic loss: ", critic_loss.item())
        self.critic_optimizer.step()

        # update priorities
        priorities = (((current_Q1 - target_Q).detach()**2)*self.alpha).cpu().squeeze(1).numpy() \
                    + (((current_Q2 - target_Q).detach()**2)*self.alpha).cpu().squeeze(1).numpy() \
                    + self.hyper_parameters_eps
        self.buffer.update_priorities(indices, priorities)

        # Delayed policy updates

        if self.total_it % self.policy_freq == 0:
            
            if (self.fix_actor_flag == False):
                # Compute actor loss
                actor_loss = -self.critic.Q1(state, self.actor(state)).mean()
                # Optimize the actor 
                self.actor_optimizer.zero_grad()
                actor_loss.backward()
                self.actor_optimizer.step()
            
            # Update the frozen target models
            for param, target_param in zip(self.critic.parameters(), self.critic_target.parameters()):
                target_param.data.copy_(self.tau * param.data + (1 - self.tau) * target_param.data)

            if (self.fix_actor_flag == False):
                for param, target_param in zip(self.actor.parameters(), self.actor_target.parameters()):
                    target_param.data.copy_(self.tau * param.data + (1 - self.tau) * target_param.data)
    

    def save(self, filename):

        torch.save(self.critic.state_dict(), filename + "_critic.pkl")
        torch.save(self.critic_optimizer.state_dict(), filename + "_critic_optimizer.pth")
        
        torch.save(self.actor.state_dict(), filename + "_actor.pkl")
        torch.save(self.actor_optimizer.state_dict(), filename + "_actor_optimizer.pth")

        self.buffer.save()

        

    def load(self, filename):

        if self.load_critic_flag == True:
            self.critic.load_state_dict(torch.load(filename + "_critic.pkl"))
            self.critic_optimizer.load_state_dict(torch.load(filename + "_critic_optimizer.pth"))
            self.critic_target = copy.deepcopy(self.critic)
            print("load critic model.")

        if self.load_actor_flag == True:
            self.actor.load_state_dict(torch.load(filename + "_actor.pkl"))
            self.actor_optimizer.load_state_dict(torch.load(filename + "_actor_optimizer.pth"))
            self.actor_target = copy.deepcopy(self.actor)
            print("load actor model.")

        if self.load_buffer_flag == True:
            self.buffer.load()
            print("load buffer data.")

        

        
                                           
  

        
                                           
  
