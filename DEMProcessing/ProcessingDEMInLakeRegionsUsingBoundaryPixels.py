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
import rasterio, rasterio.mask
from osgeo import gdal
from datetime import datetime
from datetime import date
import pathlib
import sys
import shutil
from bs4 import BeautifulSoup

class ProcessingDEMInLakeRegionsUsingBoundaryPixels(QgsProcessingAlgorithm):

    INPUTDEMLAYER = 'INPUTDEMLAYER'
    INPUTLAKESLAYER = 'INPUTLAKESLAYER'
    INPUTAOILAYER = 'INPUTAOI'
    UNIQUEFIELDNAME = 'UNIQUEFIELDNAME'
    FOLDERFORINTERMEDIATEPROCESSING = 'FOLDERFORINTERMEDIATEPROCESSING'
    OUTPUT = 'OUTPUT'

    def tr(self, string):
        """
        Returns a translatable string with the self.tr() function.
        """
        return QCoreApplication.translate('Processing', string)

    def createInstance(self):
        return ProcessingDEMInLakeRegionsUsingBoundaryPixels()

    def name(self):
        
        """
        Returns the algorithm name, used for identifying the algorithm. This
        string should be fixed for the algorithm, and must not be localised.
        The name should be unique within each provider. Names should contain
        lowercase alphanumeric characters only and no spaces or other
        formatting characters.
        """
        return 'Process DEM in lake regions using boundary pixels'


    def displayName(self):
        
        """
        Returns the translated algorithm name, which should be used for any
        user-visible display of the algorithm name.
        """
        return self.tr('Process DEM in lake regions using boundary pixels')


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
        return self.tr("This algorithm will take as an input a DEM and a vector layer containing all lakes. The first step is to remove all sinks from the DEM. This happens using the "
                       "SAGA Fill Sinks (Planchon/Darboux, 2001) algorithm. It will then make the DEM completely flat in all regions containing lakes. Some important requirements are that in the " +
                       "vector layer, each lake is a separate polygon and there exists a field which is unique for each lake (likely an id). Also, makes sure that the input lakes layer is in exactly the " + 
                       "same coordinate system and projection as the input DEM (for example UTM34N and UTM35N will not work). The algorithm takes the average elevation value of all pixels on the boundary of each lake and outputs a new DEM, where each " 
                       "pixel value within the lake is set to the average elevation value for the boundary for that lake. \n" +
                       "Prerequisites that need to be installed in QGIS (mandatory in order for this algorithm to work): \n" +
                       "* SAGA Next Generation (with SAGA version greater than 9.1)\n" +
                       "* gdal\n" +
                       "* Beautiful Soup - a python library for HTML parsing, to install it follow these steps: \n" +
                       " \t - In QGIS, go to Plugins -> Python console \n" +
                       " \t - Type \"import pip\" \n" +
                       " \t - Type \"pip.main([\"install\",\"bs4\"])\" ")


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
                self.INPUTLAKESLAYER,
                self.tr('Input lakes layer'),
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
            QgsProcessingParameterField(
                self.UNIQUEFIELDNAME,
                 self.tr('Field name of unique id for each lake'),
                type=QgsProcessingParameterField.Any,
                parentLayerParameterName=self.INPUTLAKESLAYER,
                defaultValue=None)
        )
        
        self.addParameter(
            QgsProcessingParameterFile(
                self.FOLDERFORINTERMEDIATEPROCESSING,
                self.tr("Processing folder - a directory with the current date will get created within this folder, and it will hold all the intermiediate files"),
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
        
        working_dir_path = os.path.join(dir_path, "PROCESS_DEM_IN_LAKE_REGIONS_USING_BOUNDARY_PIXELS-" + current_date_and_time)
        os.mkdir(working_dir_path) 

        # split up the lakes layer into individual shape files for each lake
        parameters_split_vector_layer = {'INPUT': parameters["INPUTLAKESLAYER"],
                      'FIELD': parameters["UNIQUEFIELDNAME"],
                      'FILE_TYPE': 1,
                      'OUTPUT': working_dir_path}
                                            
        processing.run('qgis:splitvectorlayer', parameters_split_vector_layer, context=context, feedback=feedback)
        
        individuallakesfolder = working_dir_path
        
        sinks_filled_dem = os.path.join(individuallakesfolder, 'INPUT-DEM-SINKS-FILLED.tif')
        parameters_fill_sinks = {'DEM': parameters["INPUTDEMLAYER"], 'RESULT': sinks_filled_dem}
        processing.run("saga:fillsinksplanchondarboux2001", parameters_fill_sinks)
        
        for lakeshapefilepath in glob.glob(os.path.join(individuallakesfolder, "*.shp")):
            
            lakeshapefile = QgsVectorLayer(lakeshapefilepath)
            parameters_for_polygons_to_lines = {'INPUT': lakeshapefile,
                        'OUTPUT': os.path.splitext(lakeshapefilepath)[0] + "-LINE.shp"}
            processing.run('native:polygonstolines', parameters_for_polygons_to_lines, context=context, feedback=feedback)
            
            line_for_profiling = QgsVectorLayer(os.path.splitext(lakeshapefilepath)[0] + "-LINE.shp", 'vector')
            parameters_for_profiles_from_lines = {'DEM': sinks_filled_dem,
                        'LINES': line_for_profiling,
                        'NAME': parameters["UNIQUEFIELDNAME"],
                        'PROFILE': os.path.splitext(lakeshapefilepath)[0] + "-PROFILED-POINTS.shp",
                        'PROFILES' : 'SKIP_OUTPUT'}
            processing.run('sagang:profilesfromlines', parameters_for_profiles_from_lines, context=context, feedback=feedback)
            
            resulting_points = QgsVectorLayer(os.path.splitext(lakeshapefilepath)[0] + "-PROFILED-POINTS.shp", 'vector')
            parameters_for_basic_statistics_for_field = {
                'INPUT_LAYER' : resulting_points,
                'FIELD_NAME' : 'Z',
                'OUTPUT_HTML_FILE' : os.path.splitext(lakeshapefilepath)[0] + "-STATS.html"
            }
            
            processing.run("qgis:basicstatisticsforfields", parameters_for_basic_statistics_for_field, context=context, feedback=feedback)
            
            mean_lake_elevation = ''
            
            with open(os.path.splitext(lakeshapefilepath)[0] + "-STATS.html") as html:
                
                soup = BeautifulSoup(html, "html.parser")
                #val = soup.input['Mean value:']  # val now contains the string 'THE_EMAIL_ADDRESS_HERE'
                for p in soup.select('p'):
                    text = p.get_text(strip=True, separator='\n')
                    if(text.startswith("Mean value: ")):
                        mean_lake_elevation = text.split("Mean value: ")[-1]
                        QgsMessageLog.logMessage(mean_lake_elevation, "Process DEM in lake regions using boundary pixels")
                        
            
            parameters_for_clip_raster_by_mask_layer = {'INPUT': sinks_filled_dem,
                        'MASK': lakeshapefile,
                        'OUTPUT': os.path.splitext(lakeshapefilepath)[0] + "-DEM.tif"}
            
            processing.run('gdal:cliprasterbymasklayer', parameters_for_clip_raster_by_mask_layer, context=context, feedback=feedback)
            raster = gdal.Open(os.path.splitext(lakeshapefilepath)[0] + "-DEM.tif")
            
            input_raster = QgsRasterLayer(os.path.splitext(lakeshapefilepath)[0] + "-DEM.tif", 'raster')
            output_raster = os.path.splitext(lakeshapefilepath)[0] + "-DEM-MEAN-LAKE-ELEVATION.tif"
            
            parameters_create_new_raster = {'INPUT_A' : input_raster,
                          'BAND_A' : 1,
                          'FORMULA' : mean_lake_elevation, 
                          'OUTPUT' : output_raster}
            
            processing.run('gdal:rastercalculator', parameters_create_new_raster) 
            
        
        
        mean_lake_elevation_file_paths = []

        for mean_lake_elevation_file_path in glob.glob(os.path.join(individuallakesfolder, "*-DEM-MEAN-LAKE-ELEVATION.tif")):
            
            lakeshapefile = QgsVectorLayer(lakeshapefilepath)
            mean_lake_elevation_file_paths.append(mean_lake_elevation_file_path)

        merged_lake_elevation_files = os.path.join(individuallakesfolder, 'merged-lake-elevation-files.vrt')
        vrt = gdal.BuildVRT(merged_lake_elevation_files, mean_lake_elevation_file_paths)

        result_merged_lake_elevation_files = os.path.join(individuallakesfolder, 'merged_lake_elevation_files.tif')
        gdal.Translate(result_merged_lake_elevation_files, vrt, format='GTiff')
        
        input_raster_merged_lake_elevation_files = QgsRasterLayer(result_merged_lake_elevation_files, 'raster')
        output_vector = os.path.splitext(result_merged_lake_elevation_files)[0] + "-polygon.shp"
        parameters_raster_to_vector = {'INPUT' : input_raster_merged_lake_elevation_files, 'OUTPUT' : output_vector}
        processing.run('gdal:polygonize', parameters_raster_to_vector)
        
        
        parameters_difference = {'INPUT' : parameters["INPUTAOI"], 'OVERLAY' : output_vector, 'OUTPUT' : os.path.join(individuallakesfolder, 'difference.shp')}
        processing.run('native:difference', parameters_difference)
        
        non_lakes = QgsVectorLayer(os.path.join(individuallakesfolder, 'difference.shp'))
        parameters_for_clip_raster_by_mask_layer_2 ={'INPUT': sinks_filled_dem,'MASK': non_lakes, 'OUTPUT': os.path.join(individuallakesfolder, "DEM-NON-LAKES_REGIONS.tif")}
        processing.run('gdal:cliprasterbymasklayer', parameters_for_clip_raster_by_mask_layer_2, context=context, feedback=feedback) 
        
        final_dems_to_merge = []
        final_dems_to_merge.append(os.path.join(individuallakesfolder, 'DEM-NON-LAKES_REGIONS.tif'))
        final_dems_to_merge.append(result_merged_lake_elevation_files)
        
        vrt_file = os.path.join(individuallakesfolder, 'FINAL-DEM.vrt')
        vrt_2 = gdal.BuildVRT(vrt_file, final_dems_to_merge)
        final_result = os.path.join(individuallakesfolder, "FINAL-DEM.tif")
        gdal.Translate(final_result, vrt_2, format='GTiff')

        processing.run('gdal:translate',
                   {'INPUT': final_result,
                   'DATA_TYPE':0,
                   'TFW': 1,
                   'OUTPUT': parameters["OUTPUT"]}, context = context, feedback=feedback)
        
        
        return {}