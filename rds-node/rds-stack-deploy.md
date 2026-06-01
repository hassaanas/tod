Edit /etc/netplan/50-cloud-init.yaml with the following contents:
network:
  version: 2
  ethernets:
    enp0s3:
      dhcp4: true
      dhcp4-overrides:
        use-routes: false    
    enp0s8:
      dhcp4: false
      addresses:
        - 192.168.205.77/24
      routes:
        - to: default
          via: 192.168.205.1

Then run 'sudo netplan apply'
