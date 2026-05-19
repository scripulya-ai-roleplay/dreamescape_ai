# в случае если выпадает root@ubuntu-jammy:/# docker container ls
# Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?
# https://superuser.com/questions/1741326/how-to-connect-to-docker-daemon-if-unix-var-run-docker-sock-is-not-available

sudo su
# Add Docker's official GPG key:
sudo apt-get update -y
sudo apt-get install ca-certificates curl -y
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository to Apt sources:
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update

apt-get install docker docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin -y
apt install software-properties-common python3.13-dev libffi-dev -y
add-apt-repository ppa:deadsnakes/ppa -y
apt install python3.13 python3.13-venv -y
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python3.13 get-pip.py
python3.13 -m pip install poetry
python3.13 -m venv .venv
source .venv/bin/activate
poetry lock
poetry install
