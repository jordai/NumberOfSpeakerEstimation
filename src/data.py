import tensorflow as tf 
import keras 
from keras import backend as k 
from sklearn.model_selection import train_test_split
import numpy as np
import soundfile as sf

from .util import stft

import pdb
import os
import glob



class DataSet(object):
    def __init__(self, 
                    training_dir, 
                    val_split, 
                    batch_size=32,
                    sample_rate=16000, 
                    original_sample_length=5,
                    excerpt_duration=1,
                    num_parallel_calls=4):
        self.filenames = tf.io.gfile.glob(training_dir)
        self.labels = list( map(self.obtain_label, self.filenames) )
        self.validation_split = val_split
        self.batch_size = batch_size
        self.excerpt_duration = excerpt_duration
        self.sample_rate = sample_rate
        self.original_sample_frame_length = original_sample_length * sample_rate
        self.num_parallel_calls = num_parallel_calls


    def obtain_label(self,filename):
        return filename.split("/")[-2] 

    def parse_function(self,filename):
        filepath = bytes.decode(filename.numpy())
        audio, sample_rate = sf.read(filepath)
        label = self.obtain_label(filepath)
        return tf.cast(audio, tf.float32),label
    
    def parse_function_wrapper(self, filename):
        return tf.py_function(func=self.parse_function, inp=[filename], Tout=(tf.float32, tf.string))


    def select_random_excerpt(self,file,label): #length can be changed..
        excerpt_duration = self.excerpt_duration
        excerpt_duration_frames = excerpt_duration * self.sample_rate
        limit = self.original_sample_frame_length - excerpt_duration_frames
        start = np.random.randint(0,limit)
        return tf.slice(tf.squeeze(file), [start], [excerpt_duration_frames-1]),label

    def stft_tensorflow(self, audio_tensor, label):
        data = audio_tensor.numpy()
        stft_data = stft(data)
        label = int(bytes.decode(label.numpy()))
        return tf.cast(stft_data, tf.float32),tf.convert_to_tensor(label, dtype=tf.int16)
    
    def stft_wrapper(self,audiofile, label): 
        audio, label = tf.py_function(func=self.stft_tensorflow, inp=[audiofile,label], Tout=(tf.float32,tf.int16) )
        return audio, label

    def reshape(self,audiofile, label):
        return tf.reshape(audiofile,shape=(1,100,201)), label

    def _datafactory(self, dataset):
        dataset = dataset.map(self.parse_function_wrapper, num_parallel_calls = self.num_parallel_calls)
        dataset = dataset.map(self.select_random_excerpt, num_parallel_calls = self.num_parallel_calls)
        dataset = dataset.map(self.stft_wrapper, num_parallel_calls = self.num_parallel_calls)
        dataset = dataset.map(self.reshape, num_parallel_calls = self.num_parallel_calls)
        dataset = dataset.batch(32)
        dataset = dataset.prefetch(tf.data.AUTOTUNE)
        return dataset

    def get_data(self):
        X_train, X_val, y_train, y_val = train_test_split(self.filenames, self.labels, train_size=self.validation_split, random_state=42)
        train_dataset = tf.data.Dataset.list_files(X_train)
        val_dataset = tf.data.Dataset.list_files(X_val)
        return self._datafactory(train_dataset), self._datafactory(val_dataset)



## NOTICE
## everything below this comment is most likely obsolete
class CustomDataIterator(tf.keras.preprocessing.image.DirectoryIterator):

    def __init__(self,*args,**kwargs):
        self.label_dir = kwargs.pop('label_dir')
        super(self.__class__, self).__init__(*args, **kwargs)
        self.used_indices = []

    def __getitem__(self,idx):
        if idx >= len(self):
            raise ValueError('Asked to retrieve element {idx}, '
                             'but the Sequence '
                             'has length {length}'.format(idx=idx,
                                                          length=len(self)))
        if self.seed is not None:
            np.random.seed(self.seed + self.total_batches_seen)
        self.total_batches_seen += 1
        if self.index_array is None:
            self._set_index_array()
        index_array = []
        speakers_in_batch = []
        # pdb.set_trace()
        for index in self.index_array:
            
            if index in self.used_indices:
                continue
            
            if len(speakers_in_batch) == 32:
                break

            filename = self.filepaths[index].split("/")[-1].replace(".png",".txt")
            nr_of_speakers = filename.split("_")[0]
            label_location = os.path.join(self.label_dir,nr_of_speakers,filename)
            speakers_in_sample = []
            with open(label_location) as f:
                speakers_in_sample = [line.rstrip('\n') for line in f]
            if speakers_in_sample not in speakers_in_batch:
                speakers_in_batch.append(speakers_in_sample)
                index_array.append(index)
                self.used_indices.append(index)            

        return self._get_batches_of_transformed_samples(index_array)

def custom_preprocessing(sound_sample):
    print(sound_sample.shape)



def create_tensorflow_dataset(data_dir, batch_size, data_format='channels_first',color_mode='grayscale', target_size=(500,201) ,datagenerator=None, val_split = None):
    if datagenerator is None:
        datagenerator = tf.keras.preprocessing.image.ImageDataGenerator(rescale=1./255,validation_split = val_split, preprocessing_function=custom_preprocessing)
    # train_dataset = tf.keras.preprocessing.image.DirectoryIterator(data_dir, datagenerator,batch_size=batch_size, data_format=data_format, color_mode=color_mode, target_size=target_size, subset = 'training')
    # validation_dataset = tf.keras.preprocessing.image.DirectoryIterator(data_dir, datagenerator,batch_size=batch_size, data_format=data_format, color_mode=color_mode, target_size=target_size, subset = 'validation')
    train_dataset = CustomDataIterator(data_dir, 
                            datagenerator,
                            label_dir='../data/merged_outputmetadata/',
                            batch_size=batch_size, 
                            data_format=data_format, 
                            color_mode=color_mode, 
                            target_size=target_size, 
                            subset = 'training')
    validation_dataset = CustomDataIterator(data_dir, 
                            datagenerator,
                            label_dir='../data/merged_outputmetadata/',
                            batch_size=batch_size, 
                            data_format=data_format, 
                            color_mode=color_mode, 
                            target_size=target_size, 
                            subset = 'validation')
    return train_dataset, validation_dataset

