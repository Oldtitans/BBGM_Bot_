n = 2

logn = 1
pastvalues = dict()
pastvalues.update({1:1,2:1})
import math
for i in range (1,8):
    n = n * 2
    logn += 1
    seriesvalue = pastvalues[n/2]*6-pastvalues[n/4]*8+2*n+3
    pastvalues.update({n:seriesvalue})
    print(2*n*n - 2*n-2*n*logn+1)

print(pastvalues)
