"""
Train low-data Tox21 models with graph-convolution. Test last fold only.
"""
from __future__ import print_function
from __future__ import division
from __future__ import unicode_literals

import tempfile
import numpy as np
import tensorflow as tf
import deepchem as dc
from datasets import load_tox21_convmol

# 4-fold splits
K = 4
# num positive/negative ligands
n_pos = 10
n_neg = 10
# 10 trials on test-set
n_trials = 20

tox21_tasks, dataset, transformers = load_tox21_convmol()

# Define metric
metric = dc.metrics.Metric(dc.metrics.roc_auc_score, mode="classification")

task_splitter = dc.splits.TaskSplitter()
fold_datasets = task_splitter.k_fold_split(dataset, K)

train_folds = fold_datasets[:-1] 
train_dataset = dc.splits.merge_fold_datasets(train_folds)
test_dataset = fold_datasets[-1]

# Get supports on test-set
support_generator = dc.data.SupportGenerator(
    test_dataset, n_pos, n_neg, n_trials)

# Compute accuracies
task_scores = {task: [] for task in range(len(test_dataset.get_task_names()))}

for trial_num, (task, support) in enumerate(support_generator):
  print("Starting trial %d" % trial_num)
  # Train model on support
  g = tf.Graph()
  sess = tf.Session(graph=g)

  # Do setup required for tf/keras models
  # Number of features on conv-mols
  n_feat = 75
  # Batch size of models
  batch_size = 50

  with g.as_default():
    graph_model = dc.nn.SequentialGraph(n_feat)
    graph_model.add(dc.nn.GraphConv(64, activation='relu'))
    graph_model.add(dc.nn.GraphPool())
    graph_model.add(dc.nn.GraphConv(128, activation='relu'))
    graph_model.add(dc.nn.GraphPool())
    graph_model.add(dc.nn.GraphConv(64, activation='relu'))
    graph_model.add(dc.nn.GraphPool())
    graph_model.add(dc.nn.Dense(128, activation='tanh'))
    graph_model.add(dc.nn.GraphGather(batch_size, activation="tanh"))

    with tf.Session() as sess:
      model = dc.models.MultitaskGraphClassifier(
        sess, graph_model, 1, batch_size=batch_size,
        learning_rate=1e-3, learning_rate_decay_time=1000,
        optimizer_type="adam", beta1=.9, beta2=.999)

      # Fit trained model
      model.fit(support, nb_epoch=10)

      # Test model
      task_dataset = dc.data.get_task_dataset_minus_support(
          test_dataset, support, task)
      y_pred = model.predict_proba(task_dataset)
      score = metric.compute_metric(
          task_dataset.y, y_pred, task_dataset.w)
      print("Score on task %s is %s" % (str(task), str(score)))
      task_scores[task].append(score)

# Join information for all tasks.
mean_task_scores = {}
std_task_scores = {}
for task in range(len(test_dataset.get_task_names())):
  mean_task_scores[task] = np.mean(np.array(task_scores[task]))
  std_task_scores[task] = np.std(np.array(task_scores[task]))

print("Mean scores")
print(mean_task_scores)
print("Standard Deviations")
print(std_task_scores)
print("Median of Mean Scores")
print(np.median(np.array(mean_task_scores.values())))
