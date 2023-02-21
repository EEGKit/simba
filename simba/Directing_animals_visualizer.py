__author__ = "Simon Nilsson", "JJ Choong"

import pandas as pd

from simba.Directing_animals_analyzer import DirectingOtherAnimalsAnalyzer
from simba.read_config_unit_tests import (read_config_entry,
                                          read_config_file,
                                          check_if_filepath_list_is_empty,
                                          read_project_path_and_file_type,
                                          check_file_exist_and_readable)
import os, glob
from simba.drop_bp_cords import (get_fn_ext,
                                 getBpNames,
                                 createColorListofList,
                                 create_body_part_dictionary)
from simba.misc_tools import (find_video_of_file,
                              get_video_meta_data,
                              check_multi_animal_status,
                              SimbaTimer,
                              get_color_dict)
import cv2
import numpy as np
import random
from simba.rw_dfs import read_df
from simba.enums import ReadConfig, Formats, Paths, Dtypes


class DirectingOtherAnimalsVisualizer(object):
    """
    Class for visualizing when animals are directing towards body-parts of other animals.

    > Note: Requires the pose-estimation data for the left ear, right ears and nose of individual animals.

    Parameters
    ----------
    config_path: str
        path to SimBA project config file in Configparser format

    Notes
    -----
    Requires the pose-estimation data for the ``left ear``, ``right ear`` and ``nose`` of
    each individual animals. `YouTube example of expected output <https://youtu.be/4WXs3sKu41I>`__.

    Examples
    -----
    >>> style_attr = {'Show_pose': True, 'Pose_circle_size': 3, "Direction_color": 'Random', 'Direction_thickness': 4, 'Highlight_endpoints': True}
    >>> directing_visualizer = DirectingOtherAnimalsVisualizer(config_path='/Users/simon/Desktop/envs/troubleshooting/sleap_5_animals/project_folder/project_config.ini', video_name='Testing_Video_3.mp4', style_attr=style_attr)
    >>> directing_visualizer.visualize_results()
    """


    def __init__(self,
                 config_path: str,
                 data_path: str,
                 style_attr: dict):

        self.config, self.data_path = read_config_file(config_path), data_path
        self.project_path, self.file_type = read_project_path_and_file_type(config=self.config)
        _, self.video_name, _ = get_fn_ext(self.data_path)
        self.direction_analyzer = DirectingOtherAnimalsAnalyzer(config_path=config_path)
        self.direction_analyzer.process_directionality()
        self.direction_analyzer.create_directionality_dfs()
        self.fourcc = cv2.VideoWriter_fourcc(*Formats.MP4_CODEC.value)
        self.x_cols, self.y_cols, self.pcols = getBpNames(config_path)
        self.no_animals = read_config_entry(self.config, ReadConfig.GENERAL_SETTINGS.value, ReadConfig.ANIMAL_CNT.value, Dtypes.INT.value)
        self.style_attr, self.pose_colors = style_attr, []
        self.colors = get_color_dict()
        if self.style_attr['Show_pose']:
            self.pose_colors = createColorListofList(self.no_animals, int(len(self.x_cols) + 1))
        if self.style_attr['Direction_color'] == 'Random':
            self.direction_colors = createColorListofList(1, int(self.no_animals**2))
        else:
            self.direction_colors = [self.colors[self.style_attr['Direction_color']]]
        self.data_dict = self.direction_analyzer.directionality_df_dict
        self.video_directory = os.path.join(self.project_path, 'videos')
        self.video_path = find_video_of_file(video_dir=self.video_directory, filename=self.video_name)
        self.save_directory = os.path.join(self.project_path, Paths.DIRECTING_ANIMALS_OUTPUT_PATH.value)
        if not os.path.exists(self.save_directory): os.makedirs(self.save_directory)
        self.multi_animal_status, self.multi_animal_id_lst = check_multi_animal_status(self.config, self.no_animals)
        self.animal_bp_dict = create_body_part_dictionary(self.multi_animal_status, self.multi_animal_id_lst, self.no_animals, self.x_cols, self.y_cols, [], self.pose_colors)
        self.session_timer = SimbaTimer()
        self.session_timer.start_timer()
        print(f'Processing video {self.video_name}...')

    def visualize_results(self):
        """
        Method to create directionality videos. Results are stored in
        the `project_folder/frames/output/ROI_directionality_visualize` directory of the SimBA project

        Returns
        ----------
        None
        """

        self.data_df = read_df(self.data_path, file_type=self.file_type)
        self.save_path = os.path.join(self.save_directory, self.video_name + '.mp4')
        self.cap = cv2.VideoCapture(self.video_path)
        self.video_meta_data = get_video_meta_data(self.video_path)
        self.video_data = self.data_dict[self.video_name]
        self.writer = cv2.VideoWriter(self.save_path, self.fourcc, self.video_meta_data['fps'], (self.video_meta_data['width'], self.video_meta_data['height']))
        if self.video_name in list(self.video_data['Video']):
            self.__create_video()
        else:
            print('SimBA skipping video {}: No animals are directing each other in the video.')
        self.session_timer.stop_timer()


    def __draw_individual_lines(self,
                                animal_img_data:pd.DataFrame,
                                img: np.array):

        color = self.direction_colors[0]
        for cnt, (i, r) in enumerate(animal_img_data.iterrows()):
            if self.style_attr['Direction_color'] == 'Random':
                color = random.sample(self.direction_colors[0], 1)[0]
            cv2.line(img, (int(r['Eye_x']), int(r['Eye_y'])), (int(r['Animal_2_bodypart_x']), int(r['Animal_2_bodypart_y'])), color, self.style_attr['Direction_thickness'])
            if self.style_attr['Highlight_endpoints']:
                cv2.circle(img, (int(r['Eye_x']), int(r['Eye_y'])), self.style_attr['Pose_circle_size'] + 2, color, self.style_attr['Pose_circle_size'])
                cv2.circle(img, (int(r['Animal_2_bodypart_x']), int(r['Animal_2_bodypart_y'])), self.style_attr['Pose_circle_size'] + 1, color, self.style_attr['Pose_circle_size'])

        return img


    def __create_video(self):
        img_cnt = 0
        video_timer = SimbaTimer()
        video_timer.start_timer()
        color = self.direction_colors[0]
        while (self.cap.isOpened()):
            ret, img = self.cap.read()
            try:
                if ret:
                    if self.style_attr['Show_pose']:
                        bp_data = self.data_df.iloc[img_cnt]
                        for cnt, (animal_name, animal_bps) in enumerate(self.animal_bp_dict.items()):
                            for bp in zip(animal_bps['X_bps'], animal_bps['Y_bps']):
                                x_bp, y_bp = bp_data[bp[0]], bp_data[bp[1]]
                                cv2.circle(img, (int(x_bp), int(y_bp)), self.style_attr['Pose_circle_size'], self.animal_bp_dict[animal_name]['colors'][cnt], self.style_attr['Direction_thickness'])

                    if img_cnt in list(self.video_data['Frame_#'].unique()):
                        img_data = self.video_data[self.video_data['Frame_#'] == img_cnt]
                        unique_animals = img_data['Animal_1'].unique()
                        for animal in unique_animals:
                            animal_img_data = img_data[img_data['Animal_1'] == animal].reset_index(drop=True)
                            if self.style_attr['Polyfill']:
                                convex_hull_arr = animal_img_data.loc[0, ['Eye_x', 'Eye_y']].values.reshape(-1, 2)
                                for animal_2 in animal_img_data['Animal_2'].unique():
                                    convex_hull_arr = np.vstack((convex_hull_arr, animal_img_data[['Animal_2_bodypart_x', 'Animal_2_bodypart_y']][animal_img_data['Animal_2'] == animal_2].values)).astype('int')
                                    convex_hull_arr = np.unique(convex_hull_arr, axis=0)
                                    if convex_hull_arr.shape[0] >= 3:
                                        if self.style_attr['Direction_color'] == 'Random':
                                            color = random.sample(self.direction_colors[0], 1)[0]
                                        cv2.fillPoly(img, [convex_hull_arr], color)
                                    else:
                                        img = self.__draw_individual_lines(animal_img_data=animal_img_data, img=img)

                            else:
                                img = self.__draw_individual_lines(animal_img_data=animal_img_data, img=img)

                    img_cnt += 1
                    self.writer.write(np.uint8(img))
                    print('Frame: {} / {}. Video: {})'.format(str(img_cnt), str(self.video_meta_data['frame_count']),
                                                                     self.video_name))
                else:
                    self.cap.release()
                    self.writer.release()
                    break

            except IndexError:
                self.cap.release()
                self.writer.release()



        video_timer.stop_timer()
        print('Directionality video {} saved in {} directory (elapsed time: {}s) ...'.format(self.video_name, self.save_directory, video_timer.elapsed_time_str))


# style_attr = {'Show_pose': True, 'Pose_circle_size': 3, "Direction_color": 'Random', 'Direction_thickness': 4, 'Highlight_endpoints': True, 'Polyfill': True}
# test = DirectingOtherAnimalsVisualizer(config_path='/Users/simon/Desktop/envs/troubleshooting/sleap_5_animals/project_folder/project_config.ini',
#                                        video_name='Testing_Video_3.mp4',
#                                        style_attr=style_attr)
#
# test.visualize_results()


# style_attr = {'Show_pose': True, 'Pose_circle_size': 3, "Direction_color": 'Random', 'Direction_thickness': 4, 'Highlight_endpoints': True, 'Polyfill': True}
# test = DirectingOtherAnimalsVisualizer(config_path='/Users/simon/Desktop/envs/troubleshooting/two_black_animals_14bp/project_folder/project_config.ini',
#                                        data_path='/Users/simon/Desktop/envs/troubleshooting/two_black_animals_14bp/project_folder/csv/outlier_corrected_movement_location/Together_1.csv',
#                                        style_attr=style_attr)
#
# test.visualize_results()
