# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|

  config.vm.box = "bento/ubuntu-22.04"

  config.vm.provider "virtualbox" do |vb|
    vb.memory = 2048
    vb.cpus = 2
  end

  machines = {
    "core" => {
      hostname: "core",
      networks: [
        { ip: "172.16.0.10" }
      ],
      memory: 3072,
      cpus: 2
    },

    "sensor_a" => {
      hostname: "sensor-a",
      networks: [
        { ip: "192.168.10.2" },
        { ip: "172.16.0.21" }
      ],
      memory: 2048,
      cpus: 2
    },

    "sensor_b" => {
      hostname: "sensor-b",
      networks: [
        { ip: "192.168.20.2" },
        { ip: "172.16.0.22" }
      ],
      memory: 2048,
      cpus: 2
    },

    "client_a" => {
      hostname: "client-a",
      networks: [
        { ip: "192.168.10.11" }
      ],
      memory: 1024,
      cpus: 1
    },

    "client_b" => {
      hostname: "client-b",
      networks: [
        { ip: "192.168.20.11" }
      ],
      memory: 1024,
      cpus: 1
    }
  }

  machines.each do |name, cfg|
    config.vm.define name do |node|
      node.vm.hostname = cfg[:hostname]

      cfg[:networks].each do |net|
        node.vm.network "private_network", ip: net[:ip]
      end

      node.vm.provider "virtualbox" do |vb|
        vb.name = "insider-#{name}"
        vb.memory = cfg[:memory]
        vb.cpus = cfg[:cpus]
      end

      if name == "client_b"
        node.vm.provision "ansible" do |ansible|
          ansible.playbook = "ansible/site.yml"
          ansible.limit = "all"

          ansible.groups = {
            "core" => ["core"],
            "sensors" => ["sensor_a", "sensor_b"],
            "clients" => ["client_a", "client_b"],
            "docker_hosts" => ["core", "sensor_a", "sensor_b"]
          }
        end
      end
    end
  end
end