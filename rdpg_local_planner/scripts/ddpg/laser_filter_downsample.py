#! /usr/bin/env python
#-*- coding: UTF-8 -*- 

import rospy

from sensor_msgs.msg import LaserScan

input_num = 1080
output_num = 72

class laser_filter_downsample:
    def __init__(self):

        self.laserSub = rospy.Subscriber("/iris_0/scan_filtered", LaserScan, self.laserCB)
        self.laserPub = rospy.Publisher("/iris_0/scan_downsampled", LaserScan, queue_size=1)


    def laserCB(self, msg):
        pub_msg = LaserScan()
        pub_msg.header.seq = msg.header.seq
        pub_msg.header.stamp = rospy.Time.now()
        pub_msg.header.frame_id = msg.header.frame_id
        pub_msg.angle_max = msg.angle_max
        pub_msg.angle_min = msg.angle_min
        pub_msg.angle_increment = 2.0*msg.angle_max/72.0
        pub_msg.time_increment = msg.time_increment
        pub_msg.scan_time = msg.scan_time
        pub_msg.range_max = 8.0
        pub_msg.range_min = 0.14

        for i in range(output_num):
            sum = 0.0
            count = 0
            for j in range(int(input_num/output_num)):
                if msg.ranges[int(i*(input_num/output_num)+j)] < 0.13:
                    continue
                else:
                    sum += msg.ranges[int(i*(input_num/output_num)+j)]
                    count += 1
            if count == 0:
                pub_msg.ranges.append(pub_msg.range_max)
            else:
                pub_msg.ranges.append(sum/count)

        self.laserPub.publish(pub_msg)




if __name__ == '__main__':
    rospy.init_node("laser_filter_downsample")
    instance = laser_filter_downsample()

    rospy.spin()