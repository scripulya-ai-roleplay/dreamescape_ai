Vagrant.configure("2") do |config|
  config.vm.box = "ubuntu/jammy64"
  config.vm.network "forwarded_port", guest: 80, host: 80
  config.vm.network "forwarded_port", guest: 15672, host: 15672
  config.vm.network "forwarded_port",  guest: 5672, host: 5672
  config.vm.network "forwarded_port", guest: 8080, host: 8080
  config.vm.network "forwarded_port",  guest: 3306, host: 3306
  config.vm.synced_folder ".", "/root"  # Sync your project folder
  config.vm.provision "shell", path: "provision.sh"

  config.vm.provider "virtualbox" do |vb|
     vb.memory = "1600"
     vb.cpus = "2"
  end
end
