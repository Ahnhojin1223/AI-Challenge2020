import os
import math
import datetime
import numpy as np
import time
import torch
import torch.nn as nn
from torch.optim import Adam
from torch.optim.lr_scheduler import StepLR
import argparse

from dataloader import data_loader
from evaluation import evaluation_metrics
from model import Simple_NN


try:
    from nipa import nipa_data
    DATASET_PATH = nipa_data.get_data_root('STT_child')
except:
    DATASET_PATH = os.path.join('./data')


def _infer(model, cuda, data_loader):
    res_fc = []
    res_id = []
    for index, (image_name, image, _) in enumerate(data_loader):
        if cuda :
            image = image.cuda()
        fc = model(image)
        for index, name in enumerate(image_name) :
            res_id.append(name)
            res_fc.append(fc[index])
    return [res_id, res_fc]


def feed_infer(output_file, infer_func):
    prediction_name, prediction_class = infer_func()
    predictions_str = []

    for index, name in enumerate(prediction_name):
        predictions_str.append([name, prediction_class[index]])

    with open(output_file, 'w') as file_writer:
        for item in predictions_str :
            vector = item[1].tolist()
            for i in range(len(vector)) :
                vector[i] = round(vector[i],0)
            file_writer.write(item[0] + " "+ str(vector)+'\n')

    if os.stat(output_file).st_size == 0:
        raise AssertionError('output result of inference is nothing')


def validate(prediction_file, model, validate_dataloader, validate_label_file, cuda, max_vector):
    feed_infer(prediction_file, lambda : _infer(model, cuda, data_loader=validate_dataloader))

    metric_result = evaluation_metrics(prediction_file, validate_label_file, max_vector)
    print("-------------------------------------------------")
    print('Eval result: {:.4f}'.format(metric_result))
    print("-------------------------------------------------")
    return metric_result


def test(prediction_file_name, model, test_dataloader, cudam, max_vector):
    feed_infer(prediction_file, lambda : _infer(model, cuda, data_loader=test_dataloader))


def save_model(model_name, model, optimizer, scheduler):
    state = {
        'model': model.state_dict(),
        'optimizer': optimizer.state_dict(),
        'scheduler': scheduler.state_dict()
    }
    torch.save(state, os.path.join(model_name + '.pth'))
    print('model saved')


def load_model(model_name, model, optimizer=None, scheduler=None):
    state = torch.load(os.path.join(model_name))
    model.load_state_dict(state['model'])
    if optimizer is not None:
        optimizer.load_state_dict(state['optimizer'])
    if scheduler is not None:
        scheduler.load_state_dict(state['scheduler'])
    print('model loaded')


if __name__ == '__main__':
    # mode argument
    args = argparse.ArgumentParser()
    args.add_argument("--max_vector", type=int, default=100)
    args.add_argument("--lr", type=float, default=0.0001)
    args.add_argument("--cuda", type=bool, default=False)
    args.add_argument("--num_epochs", type=int, default=4500)
    args.add_argument("--print_iter", type=int, default=10)
    args.add_argument("--model_name", type=str, default="model.pth") 
    args.add_argument("--prediction_file", type=str, default="prediction.txt")
    args.add_argument("--batch", type=int, default=8)
    args.add_argument("--mode", type=str, default="train")

    config = args.parse_args()

    max_vector = config.max_vector
    base_lr = config.lr
    cuda = config.cuda
    num_epochs = config.num_epochs
    print_iter = config.print_iter
    model_name = config.model_name
    prediction_file = config.prediction_file
    batch = config.batch
    mode = config.mode

    # create model
    model = Simple_NN(max_vector=max_vector)

    if mode == 'test':
        load_model(model_name, model)

    if cuda:
        model = model.cuda()

    if mode == 'train':
        # define loss function
        loss_fn = nn.MSELoss()
        if cuda:
            loss_fn = loss_fn.cuda()

        # set optimizer
        optimizer = Adam(
            [param for param in model.parameters() if param.requires_grad],
            lr=base_lr, weight_decay=1e-4)
        # learning decay
        scheduler = StepLR(optimizer, step_size=40, gamma=0.1)

        # get data loader
        train_dataloader, _ = data_loader(root=DATASET_PATH, phase='train', batch_size=batch, max_vector= 100)
        validate_dataloader, validate_label_file = data_loader(root=DATASET_PATH, phase='validate', batch_size=batch, max_vector= 100)
        time_ = datetime.datetime.now()
        num_batches = len(train_dataloader)
        #print("num batches : ", num_batches)

        print("------------------------------------------------------------")
        total_params = sum(p.numel() for p in model.parameters())
        print("num of parameter : ",total_params)
        trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
        print("num of trainable_ parameter :",trainable_params)
        print("------------------------------------------------------------")

        # train
        for epoch in range(num_epochs):
            model.train()
            for iter_, data in enumerate(train_dataloader):
                # fetch train data
                _, pcm_data, is_label = data 
                if cuda:
                    pcm_data = pcm_data.cuda()
                    is_label = is_label.cuda() 

                # update weight
                pred = model(pcm_data)
                #If your output is ascii following base code, you should convert ascii to char(kor)
                
                loss = loss_fn(pred, is_label)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

                if (iter_ + 1) % print_iter == 0:
                    elapsed = datetime.datetime.now() - time_
                    expected = elapsed * (num_batches / print_iter)
                    _epoch = epoch + ((iter_ + 1) / num_batches)
                    print('[{:.3f}/{:d}] loss({}) '
                          'elapsed {} expected per epoch {}'.format(
                              _epoch, num_epochs, loss.item(), elapsed, expected))
                    time_ = datetime.datetime.now()

            # scheduler update
            scheduler.step()

            # save model 
            if epoch % 500 == 0 :
                save_model(str(epoch + 1), model, optimizer, scheduler)
            # validate
            validate(prediction_file, model, validate_dataloader, validate_label_file, cuda, max_vector)
            

            time_ = datetime.datetime.now()
            elapsed = datetime.datetime.now() - time_
            print('[epoch {}] elapsed: {}'.format(epoch + 1, elapsed))

    elif mode == 'test':
        model.eval()
        # get data loader
        test_dataloader, _ = data_loader(root=DATASET_PATH, phase='test', batch_size=batch, max_vector= 100)
        test(prediction_file, model, test_dataloader, cuda, max_vector)
        # submit test result
        