from json import load
import pymysql.cursors
from numpy import zeros, uint8, argmax, savez_compressed, newaxis
from cv2 import imread, IMREAD_GRAYSCALE
from boto3 import resource
import hashlib
from subprocess import call
import time

s3_resource = resource('s3')

def lambda_handler(event, context):
    for record in event['Records']:
        bucket_name = record["messageAttributes"]["bucket"]['stringValue']
        image_path = record["messageAttributes"]["image_path"]['stringValue']
        image_meta_path = record["messageAttributes"]["meta_path"]['stringValue']
        seg_label_path = record["messageAttributes"]["segmentation_path"]['stringValue']
        imageset_meta_path = record["messageAttributes"]["set_meta_path"]['stringValue']
        
        bucket = s3_resource.Bucket(bucket_name)
        upload_time = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        imageset_id, imageset_name, user_name = parse_imageset_meta(imageset_meta_path, bucket)
        bbox_labels, has_bbox_label, image_label_class, seg_labels, has_seg_label = parse_image_meta(image_meta_path, bucket)
        
        # generate npz for seg labels (only if there are seg labels)
        if (has_seg_label): 
            image_png_path_split = image_path.split('/')
            tmp_image_png_path = '/tmp/' + image_png_path_split[-1]
            bucket.download_file(image_path, tmp_image_png_path) 
            defect_map = {}
            n = 1
            with open('/tmp/meta.json') as json_imageset_file:
                imageset_meta_json = load(json_imageset_file)
                if "defects" in imageset_meta_json:
                    for defect in imageset_meta_json["defects"]:
                        defect_map.update({imageset_meta_json["defects"][defect]["name"] : n})
                        n +=1
                  
                bucket.download_file(image_meta_path, '/tmp/image_meta.json') 
                with open('/tmp/image_meta.json') as json_image_meta_file:
                    image_meta_json = load(json_image_meta_file)
                    generate_npz(bucket, defect_map, tmp_image_png_path, image_meta_json, imageset_meta_json, seg_label_path)
            
        #hash image for image_id
        bucket.download_file(image_path, '/tmp/image.png') 
        image_id = hash_file('/tmp/image.png')
        
        # write npz to s3
        if has_seg_label:
            ### CHANGE BUCKET NAME BELOW DEPENDING ON DEV/TEST ###
            npz_bucket = s3_resource.Bucket("avi-image-label-npz-test")
            npz_bucket.upload_file('/tmp/' + image_meta_json["id"] + '.npz', image_meta_json["id"] + '.npz') 
            seg_label_npz_path = 'avi-image-label-npz' + '/' + image_meta_json["id"] + '.npz'
        
        #connect to db
        try:
            conn = pymysql.connect(
                #### CHANGE TO PRODUCTION TABLE WHEN FINISHED DEVELOPPING ###
            'avi-image-labels-metadata.crn3y3nc2obx.us-east-2.rds.amazonaws.com',
            user='admin',
            password='landingaidata',
            database='metadata',
            port=3306)
        except:
            print("error")
        
        image_path = bucket_name + "/" + image_path
        imageset_meta_path = bucket_name + "/" + imageset_meta_path
        image_meta_path = bucket_name + "/" + image_meta_path
        
        if has_seg_label:
            seg_label_path = bucket_name + "/" + seg_label_path
        else: seg_label_path = None

        #write to db
        try:
            with conn.cursor() as cursor:
                sql = "INSERT INTO `metadata` (`image_id`,`imageset_name`, `imageset_id`, `user_name`, `upload_time`, `image_label_class`, `has_seg_label`, `seg_label_classes`, `has_bbox_label`, `bbox_label`,`image_path`, `seg_label_npz_path`, `imageset_meta_path`, `image_label_folder_path`, `image_meta_path`) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                cursor.execute(sql, (image_id, imageset_name, imageset_id, user_name, upload_time, image_label_class, has_seg_label, str(defect_map), has_bbox_label, str(bbox_labels), image_path, seg_label_npz_path, imageset_meta_path, seg_label_path, image_meta_path))
            conn.commit()
        finally:
            conn.close()
        
        #clear /tmp dir 
        call('rm -rf /tmp/*', shell=True)
        
def parse_imageset_meta(imageset_meta_path=None, bucket=None):
    bucket.download_file(imageset_meta_path, '/tmp/meta.json') 
    with open('/tmp/meta.json') as json_imageset_file:
        imageset_meta_json = load(json_imageset_file)
        if "id" in imageset_meta_json:
            imageset_id = imageset_meta_json["id"]
        if "name" in imageset_meta_json:
      	    imageset_name = imageset_meta_json["name"]
        if "created_by_user" in imageset_meta_json:
            user_name = imageset_meta_json["created_by_user"]["username"]
    return imageset_id, imageset_name, user_name        
    
def parse_image_meta(image_meta_path=None, bucket=None):    
    bucket.download_file(image_meta_path, '/tmp/image_meta.json') 
    with open('/tmp/image_meta.json') as json_image_meta_file:
        image_meta_json = load(json_image_meta_file)
        if "labels" in image_meta_json:
            bbox_labels = []
            for label in image_meta_json["labels"]:
                bbox_labels.append(image_meta_json["labels"][label])
        if len(bbox_labels) == 0:
            has_bbox_label = False
        else: has_bbox_label = True    
        if "image_level_labels" in image_meta_json:
            image_label_class = None
            for label in image_meta_json["image_level_labels"]:
                image_label_class = image_meta_json["image_level_labels"][label]["label"]
        if "segmentations" in image_meta_json:
            seg_labels = []
            for seg in image_meta_json["segmentations"]:
                seg_labels.append(image_meta_json["segmentations"][seg])        
            if len(seg_labels) == 0:
          	    has_seg_label = False
            else: has_seg_label = True	
    return bbox_labels, has_bbox_label, image_label_class, seg_labels, has_seg_label        
    
def generate_npz(bucket, defect_map={}, image_png_path=None, image_meta_json=None, meta_json=None, seg_label_folder_path=None):
    defect_map.update({"ok": 0})
    npz_data_list = []
    img_shape = imread(image_png_path, 1).shape
    
    # get segmentation labels
    if "segmentations" in image_meta_json:
        all_seg_labels = []
        for seg in image_meta_json["segmentations"]:
            current_label = image_meta_json["segmentations"][seg]
            if current_label['label_set_i_d'] in meta_json["label_sets"]:
                current_label["id"] = image_meta_json["segmentations"][seg]["id"]
                current_label["color"] = meta_json["label_sets"][current_label["label_set_i_d"]]["color"]
                current_label["defect"] = meta_json["defects"][current_label["defect_i_d"]]["name"]
                current_label["image_file_name"] = seg_label_folder_path + image_meta_json["segmentations"][seg]["id"] + '.png'
                all_seg_labels.append(current_label)   
    one_hot = zeros(img_shape[:2] + (len(set(defect_map.values())),))
    defect_set = set()
        
    for seg in all_seg_labels:
        bucket.download_file(seg_label_folder_path + "/" + seg["id"] + '.png', '/tmp/' + seg["id"] + '.png')
        img_label = (imread('/tmp/' + seg["id"] + '.png', IMREAD_GRAYSCALE) > 0).astype(uint8)
        class_id = defect_map[seg["defect"]]
        defect_set.add(seg["defect"])
        one_hot[:, :, class_id] = img_label
    npz_data = argmax(one_hot, axis=2)[:, :, newaxis]
    savez_compressed('/tmp/' + image_meta_json["id"] + '.npz', npz_data)
    
def hash_file(image_file_path):
    with open(image_file_path, 'rb') as f:
        data = f.read()
    if not data:
        print("read empty file")
    sha256 = hashlib.sha256(data)
    return sha256.hexdigest()




























