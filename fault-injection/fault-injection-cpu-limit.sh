#!/bin/bash
d1=`date`
echo "Starting at $d1"
mtbf=300

for i in {1..5}
do
        broker=`microk8s.kubectl get po -n tod | grep broker | awk '{print $1}'`
        microk8s.kubectl exec -n tod $broker -- /bin/sh -c "apk add --upgrade stress-ng"
        d2=`date`
        echo "Stressing memeory limit of broker pod $broker at $d2"
        microk8s.kubectl exec -n tod $broker -- /bin/sh -c "stress-ng --vm 1 --vm-bytes 200M --timeout 2s"
        #d3=`date`
        #echo "pod deleted at $d3"
        sleep 180
        newBroker=`microk8s.kubectl get po -n tod | grep broker | awk '{print $1}'`
        newPodTime=`microk8s.kubectl logs -n tod $newBroker | grep running | awk '{print $1}' | sed 's/://'`
        echo $newPodTime
        newTime=`date -d @$newPodTime`
        echo "****************************"
        echo "Run # $i"
        echo "****************************"
        echo $newTime | awk '{print $4}'
        echo $d2 | awk '{print $4}'
        #echo $d3 | awk '{print $4}'
        echo "****************************"
        #microk8s.kubectl exec -n tod $broker -- /bin/sh -c "apk add --upgrade stress-ng"
        sleep $mtbf
done


endTime=`date`
echo "Ending at $endTime"


