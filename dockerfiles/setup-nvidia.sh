sudo usermod -aG render $USER
sudo usermod -aG video $USER
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
