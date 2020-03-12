# %%
import os, torch
import cv2 as cv
import numpy as np
from torch import nn, optim
from torch.nn import functional as F
from torch.utils.data import Dataset, DataLoader 
from torchvision import transforms, datasets, utils

# Device Configuration
device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')

# %%
SAVE_PATH = "../../../data"
URL = "https://storage.googleapis.com/download.tensorflow.org/example_images/flower_photos.tgz"
file_name = URL.split("/")[-1]
data = datasets.utils.download_and_extract_archive(URL, SAVE_PATH)
PATH = os.path.join(SAVE_PATH, "flower_photos")

category_list = [i for i in os.listdir(PATH) if os.path.isdir(os.path.join(PATH, i)) ]
print(category_list)

num_classes = len(category_list)
img_size = 150

def read_img(path, img_size):
    img = cv.imread(path)
    img = cv.cvtColor(img, cv.COLOR_BGR2RGB)
    img = cv.resize(img, (img_size, img_size))
    return img

imgs_tr = []
labs_tr = []

imgs_val = []
labs_val = []

for i, category in enumerate(category_list):
    path = os.path.join(PATH, category)
    imgs_list = os.listdir(path)
    print("Total '%s' images : %d"%(category, len(imgs_list)))
    ratio = int(np.round(0.05 * len(imgs_list)))
    print("%s Images for Training : %d"%(category, len(imgs_list[ratio:])))
    print("%s Images for Validation : %d"%(category, len(imgs_list[:ratio])))
    print("=============================")

    imgs = [read_img(os.path.join(path, img),img_size) for img in imgs_list]
    labs = [i]*len(imgs_list)

    imgs_tr += imgs[ratio:]
    labs_tr += labs[ratio:]
    
    imgs_val += imgs[:ratio]
    labs_val += labs[:ratio]

imgs_tr = np.array(imgs_tr)/255.
labs_tr = np.array(labs_tr)

imgs_val = np.array(imgs_val)/255.
labs_val = np.array(labs_val)

print(imgs_tr.shape, labs_tr.shape)
print(imgs_val.shape, labs_val.shape)

# %%
# Build network

class Inception_Module(nn.Module):
    def __init__(self, input_feature, 
                filters_b1, filters_b2_1, filters_b2_2, 
                filters_b3_1, filters_b3_2, filters_b3_3, filters_b4):
        super(Inception_Module, self).__init__()

        self.branch1 = nn.Sequential(
            nn.Conv2d(input_feature, filters_b1, 1), 
            nn.ReLU(True))

        self.branch2 = nn.Sequential(
            nn.Conv2d(input_feature, filters_b2_1, 1),
            nn.ReLU(True),
            nn.Conv2d(filters_b2_1, filters_b2_2, 3, 1, 1),
            nn.ReLU(True)
        )

        self.branch3 = nn.Sequential(
            nn.Conv2d(input_feature, filters_b3_1, 1),
            nn.ReLU(True),
            nn.Conv2d(filters_b3_1, filters_b3_2, 3, 1, 1),
            nn.ReLU(True),
            nn.Conv2d(filters_b3_2, filters_b3_3, 3, 1, 1),
            nn.ReLU(True)
        )

        self.branch4 = nn.Sequential(
            nn.AvgPool2d(3, 1, 1),
            nn.Conv2d(input_feature, filters_b4, 1),
            nn.ReLU(True)
        )

    def forward(self, x):
        return torch.cat([self.branch1(x), self.branch2(x), self.branch3(x), self.branch4(x)], dim=1)


class Grid_Reduction(nn.Module):
    def __init__(self, input_feature, filters_b1_1, filters_b1_2, 
                filters_b2_1, filters_b2_2, filters_b2_3):
        super(Grid_Reduction, self).__init__()

        self.branch1 = nn.Sequential(
            nn.Conv2d(input_feature, filters_b1_1, 1),
            nn.ReLU(True),
            nn.Conv2d(filters_b1_1, filters_b1_2, 3, 2),
            nn.ReLU(True)
        )

        self.branch2 = nn.Sequential(
            nn.Conv2d(input_feature, filters_b2_1, 1),
            nn.ReLU(True),
            nn.Conv2d(filters_b2_1, filters_b2_2, 3, 1, 1),
            nn.ReLU(True),
            nn.Conv2d(filters_b2_2, filters_b2_3, 3, 2),
            nn.ReLU(True)
        )

        self.branch3 = nn.Sequential(
            nn.MaxPool2d(3, 2)
        )
    def forward(self, x):
        return torch.cat([self.branch1(x), self.branch2(x), self.branch3(x)], dim=1)

class Auxiliary_Classifier(nn.Module):
    def __init__(self, input_feature, num_classes):
        super(Auxiliary_Classifier, self).__init__()
        self.block = nn.Sequential(
            nn.AvgPool2d(5, 3, 1),
            nn.Conv2d(input_feature, 128, 1),
            nn.ReLU(True),
            nn.AdaptiveAvgPool2d((1,1)),
            nn.Flatten(),
            nn.Linear(128, num_classes)
        )
    
    def forward(self, x):
        return self.block(x)

        
class Build_InceptionV2(nn.Module):
    def __init__(self, input_channel=3, num_classes=1000):
        super(Build_InceptionV2, self).__init__()

        self.Stem = nn.Sequential(
            nn.ZeroPad2d(3),
            nn.Conv2d(3, 64, 7, 2),
            nn.ReLU(True),
            nn.MaxPool2d(3, 2),
            
            nn.Conv2d(64, 64, 1),
            nn.ReLU(True),
            nn.Conv2d(64, 192, 3, 1, 1),
            nn.ReLU(True),
            nn.MaxPool2d(3, 2)
        )
        
        self.inception1 = Inception_Module(192, 64, 64, 64, 64, 96, 96, 32)
        self.inception2 = Inception_Module(256, 64, 64, 96, 64, 96, 96, 64)
        self.grid_reduction1 = Grid_Reduction(320, 128, 160, 64, 96, 96)

        self.inception3 = Inception_Module(576, 224, 64, 96, 96, 128, 128, 128)
        self.inception4 = Inception_Module(576, 224, 64, 96, 96, 128, 128, 128)
        self.inception5 = Inception_Module(576, 160, 128, 160, 128, 160, 160, 96)
        self.inception6 = Inception_Module(576, 96, 128, 192, 160, 192, 192, 96)
        self.grid_reduction2 = Grid_Reduction(576, 128, 192, 192, 256, 256)

        self.inception7 = Inception_Module(1024, 352, 192, 160, 224, 224, 224, 128)
        self.inception8 = Inception_Module(1024, 352, 192, 320, 192, 224, 224, 128)

        self.Classifier = nn.Sequential(
            nn.AdaptiveAvgPool2d((1,1)),
            nn.Flatten(),
            nn.Dropout(0.4),
            nn.Linear(1024, num_classes)
        )
        
    def forward(self, x):
        x = self.Stem(x)
        x = self.inception1(x)
        x = self.inception2(x)
        x = self.grid_reduction1(x)
        
        x = self.inception3(x)
        x = self.inception4(x)
        x = self.inception5(x)
        x = self.inception6(x)
        x = self.grid_reduction2(x)

        x = self.inception7(x)
        x = self.inception8(x)
        x = self.Classifier(x)
        return x

inceptionv2 = Build_InceptionV2(input_channel=imgs_tr.shape[-1], num_classes=5).to(device)
criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(inceptionv2.parameters(), lr=0.001)

# %%
epochs=100
batch_size=16

class CustomDataset(Dataset):
    def __init__(self, train_x, train_y): 
        self.len = len(train_x) 
        self.x_data = torch.tensor(np.transpose(train_x, [0, 3, 1, 2]), dtype=torch.float)
        self.y_data = torch.tensor(train_y, dtype=torch.long) 

    def __getitem__(self, index): 
        return self.x_data[index], self.y_data[index] 

    def __len__(self): 
        return self.len
        
train_dataset = CustomDataset(imgs_tr, labs_tr) 
train_loader = DataLoader(dataset=train_dataset, batch_size=batch_size, shuffle=True, num_workers=2)

val_dataset = CustomDataset(imgs_val, labs_val) 
val_loader = DataLoader(dataset=val_dataset, batch_size=batch_size, shuffle=True, num_workers=2)

print("Iteration maker Done !")

# %%
# Training Network
for epoch in range(epochs):
    avg_loss = 0
    avg_acc = 0
    total_batch = train_dataset.len // batch_size
    for i, (batch_img, batch_lab) in enumerate(train_loader):
        X = batch_img.to(device)
        Y = batch_lab.to(device)

        optimizer.zero_grad()

        y_pred = inceptionv2.forward(X)

        loss = criterion(y_pred, Y)
        
        loss.backward()
        optimizer.step()
        avg_loss += loss.item()

        if (i+1)%20 == 0 :
            print("Epoch : ", epoch+1, "Iteration : ", i+1, " Loss : ", loss.item())

    with torch.no_grad():
        val_loss = 0
        total = 0
        correct = 0
        for (batch_img, batch_lab) in val_loader:
            X = batch_img.to(device)
            Y = batch_lab.to(device)
            y_pred = inceptionv2(X)
            val_loss = criterion(y_pred, Y)
            _, predicted = torch.max(y_pred.data, 1)
            total += Y.size(0)
            correct += (predicted == Y).sum().item()
        val_loss /= total
        val_acc = (100 * correct / total)

    print("Epoch : ", epoch+1, " Loss : ", (avg_loss/total_batch), " Val Loss : ", val_loss.item(), "Val Acc : ", val_acc)

print("Training Done !")