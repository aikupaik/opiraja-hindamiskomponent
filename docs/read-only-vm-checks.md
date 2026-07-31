# Read-only VM checks before HTTPS configuration
This documents serves as an extension to the plan `self-signed-https-implementation-plan.md` task 1.

## VM commands and their output
- ip -brief address
```
lo               UNKNOWN        127.0.0.1/8 ::1/128
ens3             UP             192.168.42.72/24 metric 100 fe80::f816:3eff:fe13:50f4/64
docker0          DOWN           172.17.0.1/16 fe80::6468:1aff:fefb:6644/64
br-f5aecce70208  UP             172.18.0.1/16 fe80::78e0:edff:fe58:c764/64
br-d0c23d8b0888  UP             172.19.0.1/16 fe80::6cad:86ff:fe97:e0d8/64
veth99f1dc0@if2  UP             fe80::8ca7:dff:fe51:5ed6/64
veth62b1bbf@if2  UP             fe80::ad:b0ff:fee6:a923/64
veth149238b@if3  UP             fe80::dc69:8dff:fe7b:295d/64
vethd23d71c@if2  UP             fe80::54b1:27ff:fed5:6029/64
```
- ip route
```
default via 192.168.42.1 dev ens3 proto dhcp src 192.168.42.72 metric 100
1.1.1.1 via 192.168.42.1 dev ens3 proto dhcp src 192.168.42.72 metric 100
8.8.8.8 via 192.168.42.1 dev ens3 proto dhcp src 192.168.42.72 metric 100
169.254.169.254 via 192.168.42.2 dev ens3 proto dhcp src 192.168.42.72 metric 100
172.17.0.0/16 dev docker0 proto kernel scope link src 172.17.0.1 linkdown
172.18.0.0/16 dev br-f5aecce70208 proto kernel scope link src 172.18.0.1
172.19.0.0/16 dev br-d0c23d8b0888 proto kernel scope link src 172.19.0.1
192.168.42.0/24 dev ens3 proto kernel scope link src 192.168.42.72 metric 100
192.168.42.1 dev ens3 proto dhcp scope link src 192.168.42.72 metric 100
192.168.42.2 dev ens3 proto dhcp scope link src 192.168.42.72 metric 100
```
- ss -lntup
```
Netid State  Recv-Q Send-Q       Local Address:Port   Peer Address:Port Process
udp   UNCONN 0      0               127.0.0.54:53          0.0.0.0:*
udp   UNCONN 0      0            127.0.0.53%lo:53          0.0.0.0:*
udp   UNCONN 0      0       192.168.42.72%ens3:68          0.0.0.0:*
tcp   LISTEN 0      4096         127.0.0.53%lo:53          0.0.0.0:*
tcp   LISTEN 0      4096            127.0.0.54:53          0.0.0.0:*
tcp   LISTEN 0      4096               0.0.0.0:80          0.0.0.0:*
tcp   LISTEN 0      4096               0.0.0.0:22          0.0.0.0:*
tcp   LISTEN 0      4096                  [::]:80             [::]:*
tcp   LISTEN 0      4096                  [::]:22             [::]:*
```
- docker network ls
```
NETWORK ID     NAME                         DRIVER    SCOPE
83e5df43ce06   bridge                       bridge    local
c11ac5dab853   host                         host      local
bc837d8ccf38   none                         null      local
f5aecce70208   opiraja-assessment_compute   bridge    local
d0c23d8b0888   opiraja-assessment_edge      bridge    local
```
- docker compose ps (docker ps)
```
CONTAINER ID   IMAGE                                COMMAND                  CREATED       STATUS                 PORTS                                             NAMES
1a7ac2e5200a   opiraja-assessment-web:local         "nginx -g 'daemon of…"   6 hours ago   Up 6 hours (healthy)   80/tcp, 0.0.0.0:80->8080/tcp, [::]:80->8080/tcp   opiraja-assessment-web-1
d8bb974f81b3   opiraja-assessment-api:local         "uvicorn app.main:cr…"   6 hours ago   Up 6 hours (healthy)   8000/tcp                                          opiraja-assessment-api-1
132251448f50   opiraja-assessment-r-service:local   "Rscript --vanilla -…"   6 hours ago   Up 6 hours (healthy)   8000/tcp                                          opiraja-assessment-r-service-1
```
- sudo ufw status verbose
`Status: inactive`
- sudo nft list ruleset
```
# Warning: table ip nat is managed by iptables-nft, do not touch!
table ip nat {
	chain DOCKER {
		iifname != "br-d0c23d8b0888" tcp dport 80 counter packets 23 bytes 1448 dnat to 172.19.0.3:8080
	}

	chain PREROUTING {
		type nat hook prerouting priority dstnat; policy accept;
		fib daddr type local counter packets 4052 bytes 250546 jump DOCKER
	}

	chain OUTPUT {
		type nat hook output priority dstnat; policy accept;
		ip daddr != 127.0.0.0/8 fib daddr type local counter packets 0 bytes 0 jump DOCKER
	}

	chain POSTROUTING {
		type nat hook postrouting priority srcnat; policy accept;
		ip saddr 172.19.0.0/16 oifname != "br-d0c23d8b0888" counter packets 4283 bytes 256980 masquerade
		ip saddr 172.17.0.0/16 oifname != "docker0" counter packets 45 bytes 2792 masquerade
	}
}
# Warning: table ip filter is managed by iptables-nft, do not touch!
table ip filter {
	chain DOCKER {
		ip daddr 172.19.0.3 iifname != "br-d0c23d8b0888" oifname "br-d0c23d8b0888" tcp dport 8080 counter packets 23 bytes 1448 accept
		iifname != "docker0" oifname "docker0" counter packets 0 bytes 0 drop
		iifname != "br-d0c23d8b0888" oifname "br-d0c23d8b0888" counter packets 0 bytes 0 drop
	}

	chain DOCKER-FORWARD {
		counter packets 96776 bytes 248913782 jump DOCKER-CT
		counter packets 47961 bytes 15241117 jump DOCKER-INTERNAL
		counter packets 47961 bytes 15241117 jump DOCKER-BRIDGE
		iifname "docker0" counter packets 5880 bytes 527746 accept
		iifname "br-f5aecce70208" oifname "br-f5aecce70208" counter packets 0 bytes 0 accept
		iifname "br-d0c23d8b0888" counter packets 42044 bytes 14711051 accept
	}

	chain DOCKER-BRIDGE {
		oifname "docker0" counter packets 0 bytes 0 jump DOCKER
		oifname "br-d0c23d8b0888" counter packets 37 bytes 2320 jump DOCKER
	}

	chain DOCKER-CT {
		oifname "docker0" ct state related,established counter packets 14653 bytes 206694030 accept
		oifname "br-d0c23d8b0888" ct state related,established counter packets 34162 bytes 26978635 accept
	}

	chain DOCKER-INTERNAL {
		ip saddr != 172.18.0.0/16 oifname "br-f5aecce70208" counter packets 0 bytes 0 drop
		ip daddr != 172.18.0.0/16 iifname "br-f5aecce70208" counter packets 0 bytes 0 drop
	}

	chain FORWARD {
		type filter hook forward priority filter; policy drop;
		counter packets 96776 bytes 248913782 jump DOCKER-USER
		counter packets 96776 bytes 248913782 jump DOCKER-FORWARD
	}

	chain DOCKER-USER {
	}
}
# Warning: table ip6 nat is managed by iptables-nft, do not touch!
table ip6 nat {
	chain DOCKER {
	}

	chain PREROUTING {
		type nat hook prerouting priority dstnat; policy accept;
		fib daddr type local counter packets 0 bytes 0 jump DOCKER
	}

	chain OUTPUT {
		type nat hook output priority dstnat; policy accept;
		ip6 daddr != ::1 fib daddr type local counter packets 0 bytes 0 jump DOCKER
	}
}
table ip6 filter {
	chain DOCKER {
	}

	chain DOCKER-FORWARD {
		counter packets 0 bytes 0 jump DOCKER-CT
		counter packets 0 bytes 0 jump DOCKER-INTERNAL
		counter packets 0 bytes 0 jump DOCKER-BRIDGE
	}

	chain DOCKER-BRIDGE {
	}

	chain DOCKER-CT {
	}

	chain DOCKER-INTERNAL {
	}

	chain FORWARD {
		type filter hook forward priority filter; policy accept;
		counter packets 0 bytes 0 jump DOCKER-USER
		counter packets 0 bytes 0 jump DOCKER-FORWARD
	}

	chain DOCKER-USER {
	}
}
table ip raw {
	chain PREROUTING {
		type filter hook prerouting priority raw; policy accept;
		ip daddr 172.19.0.2 iifname != "br-d0c23d8b0888" counter packets 0 bytes 0 drop
		ip daddr 172.19.0.3 iifname != "br-d0c23d8b0888" counter packets 0 bytes 0 drop
	}
}
```
- timedatectl status
```
Local time: Fri 2026-07-31 15:50:33 EEST
           Universal time: Fri 2026-07-31 12:50:33 UTC
                 RTC time: Fri 2026-07-31 12:50:33
                Time zone: Europe/Tallinn (EEST, +0300)
System clock synchronized: yes
              NTP service: active
          RTC in local TZ: no
```
- df -h
```
Filesystem      Size  Used Avail Use% Mounted on
tmpfs           1.6G  1.4M  1.6G   1% /run
/dev/sda1       193G   56G  137G  29% /
tmpfs           7.9G     0  7.9G   0% /dev/shm
tmpfs           5.0M     0  5.0M   0% /run/lock
/dev/sda16      881M  117M  703M  15% /boot
/dev/sda15      105M  6.2M   99M   6% /boot/efi
tmpfs           1.6G   12K  1.6G   1% /run/user/1000
```
- sudo nginx -T

Developer notes: Nginx is not configured locally on the VM, but by Docker. See: admin/nginx.conf