# Menu bar, results and the Studio window

[Back to README](../README.md)

## What it does

### Menu bar

* Progress, time left, and best score of every run, updated live
* GPU, CPU and memory, like Activity Monitor (Apple Silicon and NVIDIA), plus fan speed on Macs with a fan and the GPU fan on NVIDIA machines. A warning when the fans stay near full speed during training
* A notification when a run **finishes**, **fails** (loss became NaN), **stalls** (its log has not changed for a while: this is also how a crash or an out-of-memory error shows up), or **stops before its last epoch**
* A calm resting view when nothing is training
* **Just finished** card at the top: one click to the results
* **Characters that run at your training's speed**, like RunCat: a cat, a runner, a rocket, a neural net and six more. They stop when training stalls. Or upload your own GIF or frames. With nothing training, they can run with your CPU, GPU or AI tool use instead (Settings → Appearance)
* **⌥⌘E** opens the Studio window from any app, and **⌘K** jumps to anything in it. Almost every action has a keyboard shortcut

### Results

<p align="center">
  <img src="images/studio-run-detail.png" width="620" alt="A run's page: score, curves and a plain-language note on what to try next">
</p>

Click any run to see what happened, in one place:

* **Scores** at the best epoch: precision, recall, F1, mAP50, mAP50-95, per head (box, pose, mask). Hover for what each one means.
* **Curves** for loss and scores, live while training runs
* **What stands out:** plain-language notes with a next step, such as *"Recall is much higher than precision. It finds most objects but raises many false alarms."*
* **Per class:** precision, recall and mAP for each class, weakest first, with the ones well below the average highlighted. Saved at the end of runs Epokio starts; one click works it out for any other Ultralytics run
* **The machine while training:** GPU (the first one on that machine), GPU memory, CPU, memory, temperature and fan recorded every 15 seconds while the run trains (runs training at the same time share these numbers), with a note when the GPU was mostly waiting
* **Predictions by epoch** (turn it on when you start a run): the same four validation images every 5 epochs, on a slider
* **Data version:** which version of the dataset the run used (*Data v3 of 4*), and a warning with what changed if the data changed afterwards
* **Result images** your framework saved (curves, confusion matrix, predictions next to your labels), also from remote machines
* **How it was run:** for runs started from Epokio, the Python, PyTorch, Ultralytics and CUDA versions, the GPU, the git commit and the seed, so you can run it again the same way
* **Next steps:** try this model, review its mistakes, train again with the same settings, or resume a stopped run from `weights/last.pt`

**Compare** up to eight runs on one chart and in one table, with a list of only the settings that differed. **Sweeps** try several settings and rank them, with a parallel coordinates chart that shows which values led to the best score. **Notifications** stay in the bell at the top right, so a run that finished overnight is still there in the morning.

<p align="center">
  <img src="images/studio-compare.png" width="620" alt="Compare: one chart for several runs, their scores, and only the settings that differed">
</p>

### Studio window

<p align="center">
  <img src="images/studio-home.png" width="620" alt="Home: what is running, what needs attention, recent results">
</p>

<p align="center">
  <img src="images/studio-train.png" width="620" alt="Studio, new training">
</p>

**For beginners:** drop your `data.yaml` and Epokio checks it first: missing labels, classes with no examples, a validation set that is too small, very unbalanced classes. No dataset yet? Start with a tiny 8-image sample. Then pick a task (detect, segment, pose, classify), a model size and
the number of epochs, then press Start.

**For experts:** turn on *Show all settings* to get every training option of your installed Ultralytics
version, with its description. The list is generated from Ultralytics' own config file, so it stays
current when Ultralytics updates.

* **Try it:** drop an image and see what your model finds, with class names and confidence. Uses the CPU while a training run is using the GPU.
* **Datasets:** see your images with their YOLO boxes and pose keypoints drawn on top, and fix them: draw and move boxes, zoom and pan, pick classes from the keyboard (a searchable list when there are more than ten), and every change saves as you go. Boxes a model made are marked apart from the ones you checked. Filter by class, find images with no label, flip through with the arrow keys.
* **Review:** find your best and worst images. Labels are drawn in green, predictions in red, so you see at once what the model missed or invented. Mark each one as *model wrong*, *label wrong* or *not sure* with one key, and get a CSV for fixing labels or retraining.
* **Queue:** one job at a time on each GPU (a machine with several NVIDIA GPUs runs one per GPU), survives restarts, reorder and cancel, live logs
* **Practice:** a pretend training run to learn the screens with no GPU and no data, and a short tour for your first real run. Neither starts real training by itself.
* **Auto-label:** pick a model and a folder of images. Labels are written to a separate `labels_auto/`
  folder, so your existing labels are never overwritten. You get a summary of what to review.
* **Reports:** a Markdown report with a leaderboard, precision, recall, F1 and mAP per head,
  the charts your framework produced, and plain-language notes such as
  *"Validation loss bottomed at epoch 32 and rose afterwards. The model may be overfitting."*

<p align="center">
  <img src="images/studio-datasets.png" width="620" alt="Datasets, labels drawn on images">
</p>

## Side features

These moved here from the main README. On the web page, **Review** and **Sweeps** are under **More** in the tab bar.

| Framework | Start runs | Auto-label, review |
|---|---|---|
| Ultralytics YOLO | from the app or the web page | yes |
| Hugging Face Trainer, Lightning, Keras, TensorBoard, MAE/DeiT `log.txt`, timm, OpenMMLab, W&B, your own loop | as a script job | |

* The label editor and starting auto-label jobs are Mac only. The web page covers watching, training, the queue, compare, review, sweeps and alerts.
* The menu bar characters, compare and sweeps, data versions and the dataset views are described in the sections above.
