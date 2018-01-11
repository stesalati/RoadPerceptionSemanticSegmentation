import numpy as np
import matplotlib.pyplot as plt

# Measured - Calculated
indoor_120 = np.asarray([[2933, 2510],
                     [3780, 3130],
                     [4769, 3800],
                     [5647, 4290],
                     [7070, 5020],
                     [8208, 5660],
                     [9366, 6190],
                     [10756, 6660],
                     [12048, 7190],
                     [13096, 7610],
                     [14302, 7830],
                     [15229, 8320],
                     [16273, 8590]])

outdoor_120 = np.asarray([[3188, 2720],
                      [4890, 3860],
                      [6261, 4670],
                      [8335, 5660],
                      [10094, 6490],
                      [12290, 7190],
                      [14861, 8070],
                      [17412, 8870],
                      [20144, 9510],
                      [22545, 9860],
                      [24888, 10200]])
                      
outdoor_60 = np.asarray([[1650, ],
                         [3330, ],
                         [5160, ],
                         [6983, ],
                         [8740, ],
                         [10557, ],
                         [12628, ],
                         [14992, ],
                         [17416, ],
                         [19699, ],
                         [19997, ],
                         [22595, ],
                         [25424, ],
                         [28217, ],
                         [31020, ],
                         [34055, ],
                         [37304, ],
                         [25864, ],
                         [21921, ],
                         [18906, ],
                         [15393, ],
                         [12057, ],
                         [8945, ],
                         [6463, ],
                         [4168, ],
                         [2784, ],
                         [1616, ]])

data = np.vstack((indoor, outdoor))
print(data)

p = np.polyfit(data[:,1], data[:,0], 2)
print(p)

r  = np.polyval(p, data[:,1]) - data[:,0]
print(r)


fig = plt.figure(1)
plt.plot(data[:,1], data[:,0], '.')
plt.xlabel('Reprojected from disparity map')
plt.ylabel('Laser (true) measurement')
plt.grid(1)
# plt.hist(r)
plt.show()
