# -*- coding: utf-8 -*-

"""
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import (QgsProcessing,
                       QgsFeatureSink,
                       QgsProcessingException,
                       QgsProcessingAlgorithm,
                       QgsProcessingParameterFeatureSource,
                       QgsProcessingParameterRasterLayer,
                       QgsProcessingParameterString,
                       QgsProcessingParameterField,
                       QgsProcessingParameterRasterDestination,
                       QgsProcessingParameterFeatureSink,
                       QgsRasterLayer,
                       QgsVectorLayer,
                       QgsMessageLog,
                       QgsProcessingParameterFile,
                       Qgis,
                       QgsPathResolver)
from qgis import processing
import numpy
import glob
import os
from osgeo import gdal
from datetime import datetime
from datetime import date
import pathlib
import sys
import shutil
from bs4 import BeautifulSoup

class ProcessingDEMWithOneLakeInRegion(QgsProcessingAlgorithm):

    INPUTDEMLAYER = 'INPUTDEMLAYER'
    INPUTLAKELAYER = 'INPUTLAKELAYER'
    INPUTAOILAYER = 'INPUTAOI'
    ELEVATIONOFLAKE = 'ELEVATIONOFLAKE'
    FOLDERFORINTERMEDIATEPROCESSING = 'FOLDERFORINTERMEDIATEPROCESSING'
    OUTPUT = 'OUTPUT'

    def tr(self, string):
        """
        Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return ProcessingDEMWithOneLakeInRegion()

    def name(self):
        
        """
        Returns the algorithm name, used for identifying the algorithm. This
        string should be fixed for the algorithm, and must not be localised.
        The name should be unique within each provider. Names should contain
        lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return 'Process DEM with 1 lake in region'


    def displayName(self):
        
        """
        Returns the translated algorithm name, which should be used for any
        user-visible display of the algorithm name.
        """
        return self.tr('Process DEM with 1 lake in region')


    def group(self):
        
        """
        Returns the name of the group this algorithm belongs to. This string
        should be localised.
        """
        return self.tr('Helper scripts')


    def groupId(self):
        
        """
        Returns the unique ID of the group this algorithm belongs to. This
        string should be fixed for the algorithm, and must not be localised.
        The group id should be unique within each provider. Group id should
        contain lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return 'helperscripts'


    def shortHelpString(self):
        
        """
        Returns a localised short helper string for the algorithm. This string
        should provide a basic description about what the algorithm does and the
        parameters and outputs associated with it..
        """
        return self.tr("This algorithm will take as an input a DEM and a vector layer containing the lake. It will make the DEM completely flat where the lake is located. Make sure that the input lake layer is in exactly the " + 
                       "same coordinate system and projection as the input DEM (for example UTM34N and UTM35N will not work). The algorithm takes the input elevation value for the lake and outputs a new DEM, where each " 
                       "pixel value within the lake is set to this input elevation value.")

    def initAlgorithm(self, config=None):
        
        """
        Here we define the inputs and output of the algorithm, along
        with some other properties.
        """
        self.addParameter(
            QgsProcessingParameterRasterLayer(
                self.INPUTDEMLAYER,
                self.tr('Input DEM layer')
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUTLAKELAYER,
                self.tr('Input lake layer'),
                [QgsProcessing.TypeVector]
            )
        )
        
        self.addParameter(
            QgsProcessingParameterFeatureSource(
                self.INPUTAOILAYER,
                self.tr('Area of interest - should coincide with the input DEM layer!'),
                [QgsProcessing.TypeVector]
            )
        )
        
        self.addParameter(
            QgsProcessingParameterString(
                self.ELEVATIONOFLAKE,
                self.tr('Elevation of the lake in meters')
                )
            )
        
        self.addParameter(
            QgsProcessingParameterFile(
                self.FOLDERFORINTERMEDIATEPROCESSING,
                self.tr("Processing folder - a directory with the current date will get created within this folder, and it will hold all the intermediate files"),
                behavior=QgsProcessingParameterFile.Folder
                )
        )
        
        self.addParameter(
            QgsProcessingParameterRasterDestination(
                self.OUTPUT,
                self.tr('Output layer')
            )
        )


    def processAlgorithm(self, parameters, context, feedback):
        
        dir_path = parameters['FOLDERFORINTERMEDIATEPROCESSING']
        current_date = date.today()
        current_date_and_time = str(current_date) + "-" + datetime.now().strftime("%H:%M:%S").replace(":","")
        
        working_dir_path = os.path.join(dir_path, "PROCESS_DEM_WITH_1_LAKE_IN_REGION-" + current_date_and_time)
        os.mkdir(working_dir_path) 
        
        lakeshapefile = QgsVectorLayer(parameters["INPUTLAKELAYER"])
        mean_lake_elevation = parameters["ELEVATIONOFLAKE"]
        
        dem_in_lake = os.path.join(working_dir_path, "DEM-IN-LAKE.tif")
        
        parameters_for_clip_raster_by_mask_layer = {'INPUT': parameters["INPUTDEMLAYER"],
                'MASK': parameters["INPUTLAKELAYER"],
                'OUTPUT': dem_in_lake}
        processing.run('gdal:cliprasterbymasklayer', parameters_for_clip_raster_by_mask_layer, context=context, feedback=feedback)
                
        input_raster = QgsRasterLayer(dem_in_lake, 'raster')
        output_raster = os.path.splitext(dem_in_lake)[0] + "-DEM-SET-TO-INPUT-LAKE-ELEVATION.tif"
            
        parameters_create_new_raster = {'INPUT_A' : input_raster,
                'BAND_A' : 1,
                'FORMULA' : mean_lake_elevation, 
                'OUTPUT' : output_raster}
        processing.run('gdal:rastercalculator', parameters_create_new_raster)
                
        output_vector = os.path.splitext(output_raster)[0] + "-polygon.shp"
        parameters_raster_to_vector = {'INPUT' : output_raster, 'OUTPUT' : output_vector}
        processing.run('gdal:polygonize', parameters_raster_to_vector)
        
        
        parameters_difference = {'INPUT' : parameters["INPUTAOI"], 'OVERLAY' : output_vector, 'OUTPUT' : os.path.join(working_dir_path, 'difference.shp')}
        processing.run('native:difference', parameters_difference)
        
        non_lake = QgsVectorLayer(os.path.join(working_dir_path, 'difference.shp'))
        parameters_for_clip_raster_by_mask_layer_2 ={'INPUT': parameters["INPUTDEMLAYER"],'MASK': non_lake, 'OUTPUT': os.path.join(working_dir_path, "DEM-NON-LAKE-REGION.tif")}
        processing.run('gdal:cliprasterbymasklayer', parameters_for_clip_raster_by_mask_layer_2, context=context, feedback=feedback) 
        
        final_dems_to_merge = []
        final_dems_to_merge.append(os.path.join(working_dir_path, "DEM-NON-LAKE-REGION.tif"))
        final_dems_to_merge.append(output_raster)
        
        vrt_file = os.path.join(working_dir_path, 'FINAL-DEM.vrt')
        vrt_2 = gdal.BuildVRT(vrt_file, final_dems_to_merge)
        final_result = os.path.join(working_dir_path, "FINAL-DEM.tif")
        gdal.Translate(final_result, vrt_2, format='GTiff')

        processing.run('gdal:translate',
                   {'INPUT': final_result,
                   'DATA_TYPE':0,
                   'TFW': 1,
                   'OUTPUT': parameters["OUTPUT"]}, context = context, feedback=feedback)
        
        
        return {}