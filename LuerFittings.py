#Author-Nico Schlueter
#Description-Add-In for creating Luer Fittings

import adsk.core, adsk.fusion, adsk.cam, traceback
import math


# Global set of event handlers to keep them referenced for the duration of the command
_handlers = []

COMMAND_ID = "luerFittings"
COMMAND_NAME = "Luer Fitting"
COMMAND_TOOLTIP = "Creates a luer fitting"

# Initial persistence Dict
pers = {
    'DDType': "Male Slip",
    "VIDiametralClearance": 0,
    "VIHole": 0.225
}

# Fires when the CommandDefinition gets executed.
# Responsible for adding commandInputs to the command &
# registering the other command handlers.
class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global pers

            # Get the command that was created.
            cmd = adsk.core.Command.cast(args.command)
            
            # Registers the CommandExecutePreviewHandler
            onExecutePreview = CommandExecutePreviewHandler()
            cmd.executePreview.add(onExecutePreview)
            _handlers.append(onExecutePreview)
            
            # Registers the CommandInputChangedHandler          
            onInputChanged = CommandInputChangedHandler()
            cmd.inputChanged.add(onInputChanged)
            _handlers.append(onInputChanged)            
            
            # Registers the CommandValidateInputsEventHandler
            onValidate = CommandValidateInputsEventHandler()
            cmd.validateInputs.add(onValidate)
            _handlers.append(onValidate)

                
            # Get the CommandInputs collection associated with the command.
            inputs = cmd.commandInputs

            siOrigin = inputs.addSelectionInput("SIOrigin", "Point", "Select Center Point")
            siOrigin.addSelectionFilter("ConstructionPoints")
            siOrigin.addSelectionFilter("SketchPoints")
            siOrigin.addSelectionFilter("Vertices")
            siOrigin.addSelectionFilter("CircularEdges")
            siOrigin.setSelectionLimits(1, 1)
            siOrigin.tooltip = "Fitting Center Point"
            siOrigin.tooltipDescription = "Select the center point of the Fitting.\nWill be projected onto the plane.\n\nValid selections:\n    Sketch Points\n    Construction Points\n    BRep Vertices\n    Circular BRep Edges\n"

            siPlane = inputs.addSelectionInput("SIPlane", "Plane", "Select Fitting Plane")
            siPlane.addSelectionFilter("ConstructionPlanes")
            siPlane.addSelectionFilter("PlanarFaces")
            siPlane.setSelectionLimits(0, 1)
            siPlane.tooltip = "Gear Plane"
            siPlane.tooltipDescription = "Select the plane the fitting will be placed on.\n\nValid selections are:\n    Construction Planes\n    BRep Faces\n\nNot needed if SketchPoint is selected."
            
            ddType = inputs.addDropDownCommandInput("DDType", "Type", 0)
            ddType.listItems.add("Male Slip", pers["DDType"] == "Male Slip", "")
            ddType.listItems.add("Male Lock", pers["DDType"] == "Male Lock", "")
            ddType.listItems.add("Male Lock (internal)", pers["DDType"] == "Male Lock (internal)", "")
            ddType.listItems.add("Female Slip", pers["DDType"] == "Female Slip", "")
            ddType.listItems.add("Female Slip (internal)", pers["DDType"] == "Female Slip (internal)", "")
            ddType.listItems.add("Female Lock", pers["DDType"] == "Female Lock", "")

            viHole = inputs.addValueInput("VIHole", "Hole diameter", "mm", adsk.core.ValueInput.createByReal(pers["VIHole"]))
            
            viDiametralClearance = inputs.addValueInput("VIDiametralClearance", "Clearance (diametral)", "mm", adsk.core.ValueInput.createByReal(pers["VIDiametralClearance"]))

           
        except:
            print(traceback.format_exc())



# Fires when the Command is being created or when Inputs are being changed
# Responsible for generating a preview of the output.
# Changes done here are temporary and will be cleaned up automatically.
class CommandExecutePreviewHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            eventArgs = adsk.core.CommandEventArgs.cast(args)
            
            app = adsk.core.Application.get()
            des = app.activeProduct
            root = des.rootComponent
            comp = des.activeComponent

            # Saves setting to persistance dictionary
            global pers
            pers["DDType"] = args.command.commandInputs.itemById("DDType").selectedItem.name
            pers["VIDiametralClearance"] = args.command.commandInputs.itemById("VIDiametralClearance").value
            pers["VIHole"] = args.command.commandInputs.itemById("VIHole").value

            # Gets point object and calculates its Point3D
            point = args.command.commandInputs.itemById("SIOrigin").selection(0).entity
            pointPrim = getPrimitiveFromSelection(point)

            # Gets plane object or derives it from selected sketchPoint
            if(args.command.commandInputs.itemById("SIPlane").selectionCount == 1):
                plane = args.command.commandInputs.itemById("SIPlane").selection(0).entity
            else:
                plane = point.parentSketch.referencePlane

            # Calculates it Plane primitive
            planePrim = getPrimitiveFromSelection(plane)
            # Projects point primitive onto plane
            pointPrim = projectPointOnPlane(pointPrim, planePrim)

            # Creates a sketch on the plane object without including any geometry
            sketch = comp.sketches.addWithoutEdges(plane)

            # Gets inverse transform matrix of Sketch and transforms the point by it
            it = sketch.transform.copy()
            it.invert()
            pointPrim.transformBy(it)

            if(args.command.commandInputs.itemById("DDType").selectedItem.name == "Male Slip"):

                # Creates circle for base diameter of taper
                sketch.sketchCurves.sketchCircles.addByCenterRadius(
                    pointPrim,
                    (0.4 + math.tan(math.radians(3.44)) * 0.75 - args.command.commandInputs.itemById("VIDiametralClearance").value) / 2
                )

                # Creates circle for internal diameter
                sketch.sketchCurves.sketchCircles.addByCenterRadius(
                    pointPrim,
                    args.command.commandInputs.itemById("VIHole").value / 2
                )

                # Creates Object collection of both profiles
                oc = adsk.core.ObjectCollection.create()
                oc.add(sketch.profiles[0])
                oc.add(sketch.profiles[1])

                # Creates first extude with taper
                exturdeInput1 = comp.features.extrudeFeatures.createInput(oc, 0)
                exturdeInput1.setOneSideExtent(
                    adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString("7.5 mm")),
                    0,
                    adsk.core.ValueInput.createByString("-1.72 deg")
                )
                f1 = comp.features.extrudeFeatures.add(exturdeInput1)

                # Creates second extrude to cut internal hole
                exturdeInput2 = comp.features.extrudeFeatures.createInput(sketch.profiles[1], 1)
                exturdeInput2.setOneSideExtent(
                    adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString("7.5 mm")),
                    0,
                    adsk.core.ValueInput.createByString("0 deg")
                )
                f2 = comp.features.extrudeFeatures.add(exturdeInput2)

                if(des.designType):
                    des.timeline.timelineGroups.add(f1.timelineObject.index-1, f2.timelineObject.index)


            elif(args.command.commandInputs.itemById("DDType").selectedItem.name == "Male Lock"):

                # Creates circle for base diameter of taper
                sketch.sketchCurves.sketchCircles.addByCenterRadius(
                    pointPrim,
                    (0.4 + math.tan(math.radians(3.44)) * 0.75 - args.command.commandInputs.itemById("VIDiametralClearance").value) / 2
                )

                # Creates circle for internal diameter
                sketch.sketchCurves.sketchCircles.addByCenterRadius(
                    pointPrim,
                    args.command.commandInputs.itemById("VIHole").value / 2
                )

                # Vector maths! Yay!!!1!
                offsetODArc = adsk.core.Vector3D.create(0.142, 0.3207, 0)
                offsetCSA1 = adsk.core.Vector3D.create(0.1417, -0.0159, 0)
                offsetCSA2 = adsk.core.Vector3D.create(-0.1332 , -0.0506, 0)
                offsetLine = adsk.core.Vector3D.create(0,0,0.55)

                posODArc = pointPrim.copy()
                posODArc.translateBy(offsetODArc)

                posCSA1 = pointPrim.copy()
                posCSA1.translateBy(offsetCSA1)

                posCSA2 = pointPrim.copy()
                posCSA2.translateBy(offsetCSA2)

                offsetODArc.scaleBy(-1)
                offsetCSA1.scaleBy(-1)
                offsetCSA2.scaleBy(-1)

                posODArc2 = pointPrim.copy()
                posODArc2.translateBy(offsetODArc)

                posCSA3 = pointPrim.copy()
                posCSA3.translateBy(offsetCSA1)

                posCSA4 = pointPrim.copy()
                posCSA4.translateBy(offsetCSA2)

                posLine = pointPrim.copy()
                posLine.translateBy(offsetLine)

                
                # Creates Arcs for thread crosssection
                odArc1 = sketch.sketchCurves.sketchArcs.addByCenterStartSweep(
                    pointPrim,
                    posODArc,
                    math.radians(42.4)
                )

                sketch.sketchCurves.sketchArcs.addByCenterStartSweep(
                    posCSA1,
                    odArc1.startSketchPoint,
                    math.radians(-23)
                )

                sketch.sketchCurves.sketchArcs.addByCenterStartSweep(
                    posCSA2,
                    odArc1.endSketchPoint,
                    math.radians(23)
                )


                odArc2 = sketch.sketchCurves.sketchArcs.addByCenterStartSweep(
                    pointPrim,
                    posODArc2,
                    math.radians(42.4)
                )

                sketch.sketchCurves.sketchArcs.addByCenterStartSweep(
                    posCSA3,
                    odArc2.startSketchPoint,
                    math.radians(-23)
                )

                sketch.sketchCurves.sketchArcs.addByCenterStartSweep(
                    posCSA4,
                    odArc2.endSketchPoint,
                    math.radians(23)
                )

                pathLine = sketch.sketchCurves.sketchLines.addByTwoPoints(
                    pointPrim,
                    posLine
                )

                # Creates circle for internal diameter of threaded tube
                sketch.sketchCurves.sketchCircles.addByCenterRadius(
                    pointPrim,
                    0.4
                )

                # Creates circle for extrenal diameter of threaded tube
                sketch.sketchCurves.sketchCircles.addByCenterRadius(
                    pointPrim,
                    0.5
                )

                # Creates Object collection of both profiles
                oc1 = adsk.core.ObjectCollection.create()
                oc1.add(sketch.profiles[0])
                oc1.add(sketch.profiles[1])

                # Creates first extude with taper
                exturdeInput1 = comp.features.extrudeFeatures.createInput(oc1, 0)
                exturdeInput1.setOneSideExtent(
                    adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString("7.5 mm")),
                    0,
                    adsk.core.ValueInput.createByString("-1.72 deg")
                )
                f1 = comp.features.extrudeFeatures.add(exturdeInput1)

                # Creates second extrude to cut internal hole
                exturdeInput2 = comp.features.extrudeFeatures.createInput(sketch.profiles[1], 1)
                exturdeInput2.setOneSideExtent(
                    adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString("7.5 mm")),
                    0,
                    adsk.core.ValueInput.createByString("0 deg")
                )
                comp.features.extrudeFeatures.add(exturdeInput2)

                # Creates third extrude to join threaded tube
                exturdeInput3 = comp.features.extrudeFeatures.createInput(sketch.profiles[5], 0)
                exturdeInput3.setOneSideExtent(
                    adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString("5.5 mm")),
                    0,
                    adsk.core.ValueInput.createByString("0 deg")
                )
                comp.features.extrudeFeatures.add(exturdeInput3)

                # Creates Object collection of thread wings
                oc2 = adsk.core.ObjectCollection.create()
                oc2.add(sketch.profiles[2])
                oc2.add(sketch.profiles[4])

                path = comp.features.createPath(pathLine)
                sweepInput = comp.features.sweepFeatures.createInput(oc2, path, 0)
                sweepInput.twistAngle = adsk.core.ValueInput.createByReal(math.radians(396))
                f2 = comp.features.sweepFeatures.add(sweepInput)

                if(des.designType):
                    des.timeline.timelineGroups.add(f1.timelineObject.index-1, f2.timelineObject.index)


            elif(args.command.commandInputs.itemById("DDType").selectedItem.name == "Male Lock (internal)"):

                pointPrim.translateBy(adsk.core.Vector3D.create(0,0,-0.55))
                

                # Creates circle for base diameter of taper
                sketch.sketchCurves.sketchCircles.addByCenterRadius(
                    pointPrim,
                    (0.4 + math.tan(math.radians(3.44)) * 0.75 - args.command.commandInputs.itemById("VIDiametralClearance").value) / 2
                )

                # Creates circle for internal diameter
                sketch.sketchCurves.sketchCircles.addByCenterRadius(
                    pointPrim,
                    args.command.commandInputs.itemById("VIHole").value / 2
                )

                # Vector maths! Yay!!!1!
                offsetODArc = adsk.core.Vector3D.create(0.142, 0.3207, 0)
                offsetCSA1 = adsk.core.Vector3D.create(0.1417, -0.0159, 0)
                offsetCSA2 = adsk.core.Vector3D.create(-0.1332 , -0.0506, 0)
                offsetLine = adsk.core.Vector3D.create(0,0,0.55)

                posODArc = pointPrim.copy()
                posODArc.translateBy(offsetODArc)

                posCSA1 = pointPrim.copy()
                posCSA1.translateBy(offsetCSA1)

                posCSA2 = pointPrim.copy()
                posCSA2.translateBy(offsetCSA2)

                offsetODArc.scaleBy(-1)
                offsetCSA1.scaleBy(-1)
                offsetCSA2.scaleBy(-1)

                posODArc2 = pointPrim.copy()
                posODArc2.translateBy(offsetODArc)

                posCSA3 = pointPrim.copy()
                posCSA3.translateBy(offsetCSA1)

                posCSA4 = pointPrim.copy()
                posCSA4.translateBy(offsetCSA2)

                posLine = pointPrim.copy()
                posLine.translateBy(offsetLine)

                
                # Creates Arcs for thread crosssection
                odArc1 = sketch.sketchCurves.sketchArcs.addByCenterStartSweep(
                    pointPrim,
                    posODArc,
                    math.radians(42.4)
                )

                sketch.sketchCurves.sketchArcs.addByCenterStartSweep(
                    posCSA1,
                    odArc1.startSketchPoint,
                    math.radians(-23)
                )

                sketch.sketchCurves.sketchArcs.addByCenterStartSweep(
                    posCSA2,
                    odArc1.endSketchPoint,
                    math.radians(23)
                )


                odArc2 = sketch.sketchCurves.sketchArcs.addByCenterStartSweep(
                    pointPrim,
                    posODArc2,
                    math.radians(42.4)
                )

                sketch.sketchCurves.sketchArcs.addByCenterStartSweep(
                    posCSA3,
                    odArc2.startSketchPoint,
                    math.radians(-23)
                )

                sketch.sketchCurves.sketchArcs.addByCenterStartSweep(
                    posCSA4,
                    odArc2.endSketchPoint,
                    math.radians(23)
                )

                pathLine = sketch.sketchCurves.sketchLines.addByTwoPoints(
                    pointPrim,
                    posLine
                )

                # Creates circle for internal diameter of threaded tube
                sketch.sketchCurves.sketchCircles.addByCenterRadius(
                    pointPrim,
                    0.4
                )

                # Creates circle for extrenal diameter of threaded tube
                sketch.sketchCurves.sketchCircles.addByCenterRadius(
                    pointPrim,
                    0.5
                )

                # Creates Object collection of thread wings
                oc2 = adsk.core.ObjectCollection.create()
                oc2.add(sketch.profiles[0])
                oc2.add(sketch.profiles[1])
                oc2.add(sketch.profiles[3])

                path = comp.features.createPath(pathLine)
                sweepInput = comp.features.sweepFeatures.createInput(oc2, path, 1)
                sweepInput.twistAngle = adsk.core.ValueInput.createByReal(math.radians(396))
                f1 = comp.features.sweepFeatures.add(sweepInput)




                # Creates Object collection of both profiles
                oc1 = adsk.core.ObjectCollection.create()
                oc1.add(sketch.profiles[0])
                oc1.add(sketch.profiles[1])

                # Creates first extude with taper
                exturdeInput1 = comp.features.extrudeFeatures.createInput(oc1, 0)
                exturdeInput1.setOneSideExtent(
                    adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString("7.5 mm")),
                    0,
                    adsk.core.ValueInput.createByString("-1.72 deg")
                )
                comp.features.extrudeFeatures.add(exturdeInput1)

                # Creates second extrude to cut internal hole
                exturdeInput2 = comp.features.extrudeFeatures.createInput(sketch.profiles[1], 1)
                exturdeInput2.setOneSideExtent(
                    adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString("7.5 mm")),
                    0,
                    adsk.core.ValueInput.createByString("0 deg")
                )
                f2 = comp.features.extrudeFeatures.add(exturdeInput2)

                if(des.designType):
                    des.timeline.timelineGroups.add(f1.timelineObject.index-1, f2.timelineObject.index)

            
            elif(args.command.commandInputs.itemById("DDType").selectedItem.name == "Female Slip"):

                # Creates circle for outside diameter
                sketch.sketchCurves.sketchCircles.addByCenterRadius(
                    pointPrim,
                    0.65/2
                )

                # Creates circle for base diameter of taper
                sketch.sketchCurves.sketchCircles.addByCenterRadius(
                    pointPrim,
                    (0.43 - math.tan(math.radians(3.44)) * 0.9 + args.command.commandInputs.itemById("VIDiametralClearance").value) / 2
                )

                # Creates extude cut with taper
                exturdeInput1 = comp.features.extrudeFeatures.createInput(sketch.profiles[0], 0)
                exturdeInput1.setOneSideExtent(
                    adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString("9 mm")),
                    0,
                    adsk.core.ValueInput.createByString("0 deg")
                )
                f1 = comp.features.extrudeFeatures.add(exturdeInput1)

                # Creates extude cut with taper
                exturdeInput2 = comp.features.extrudeFeatures.createInput(sketch.profiles[1], 1)
                exturdeInput2.setOneSideExtent(
                    adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString("9 mm")),
                    0,
                    adsk.core.ValueInput.createByString("1.72 deg")
                )
                f2 = comp.features.extrudeFeatures.add(exturdeInput2)

                if(des.designType):
                    des.timeline.timelineGroups.add(f1.timelineObject.index-1, f2.timelineObject.index)


            elif(args.command.commandInputs.itemById("DDType").selectedItem.name == "Female Slip (internal)"):

                # Creates circle for base diameter of taper
                sketch.sketchCurves.sketchCircles.addByCenterRadius(
                    pointPrim,
                    (0.43 + args.command.commandInputs.itemById("VIDiametralClearance").value) / 2
                )

                # Creates extude cut with taper
                exturdeInput1 = comp.features.extrudeFeatures.createInput(sketch.profiles[0], 1)
                exturdeInput1.setOneSideExtent(
                    adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString("-9 mm")),
                    0,
                    adsk.core.ValueInput.createByString("-1.72 deg")
                )
                f1 = comp.features.extrudeFeatures.add(exturdeInput1)

                if(des.designType):
                    des.timeline.timelineGroups.add(f1.timelineObject.index-1, f1.timelineObject.index)


            elif(args.command.commandInputs.itemById("DDType").selectedItem.name == "Female Lock"):

                # Creates circle for outside diameter
                sketch.sketchCurves.sketchCircles.addByCenterRadius(
                    pointPrim,
                    0.67/2
                )

                # Creates circle for base diameter of taper
                sketch.sketchCurves.sketchCircles.addByCenterRadius(
                    pointPrim,
                    (0.43 - math.tan(math.radians(3.44)) * 0.9 + args.command.commandInputs.itemById("VIDiametralClearance").value) / 2
                )

                # Vector maths! Yay!!!1!
                offsetODArc = adsk.core.Vector3D.create(-0.124, 0.3695, 0)
                offsetCSA1 = adsk.core.Vector3D.create(-0.1487, 0.0435, 0)
                offsetCSA2 = adsk.core.Vector3D.create(-0.0156 , 0.1534, 0)
                offsetLine = adsk.core.Vector3D.create(0,0,0.9)

                posODArc = pointPrim.copy()
                posODArc.translateBy(offsetODArc)

                posCSA1 = pointPrim.copy()
                posCSA1.translateBy(offsetCSA1)

                posCSA2 = pointPrim.copy()
                posCSA2.translateBy(offsetCSA2)

                offsetODArc.scaleBy(-1)
                offsetCSA1.scaleBy(-1)
                offsetCSA2.scaleBy(-1)

                posODArc2 = pointPrim.copy()
                posODArc2.translateBy(offsetODArc)

                posCSA3 = pointPrim.copy()
                posCSA3.translateBy(offsetCSA1)

                posCSA4 = pointPrim.copy()
                posCSA4.translateBy(offsetCSA2)

                posLine = pointPrim.copy()
                posLine.translateBy(offsetLine)

                
                # Creates Arcs for thread crosssection
                odArc1 = sketch.sketchCurves.sketchArcs.addByCenterStartSweep(
                    pointPrim,
                    posODArc,
                    math.radians(42.4)
                )

                sketch.sketchCurves.sketchArcs.addByCenterStartSweep(
                    posCSA1,
                    odArc1.startSketchPoint,
                    math.radians(-22.8)
                )

                sketch.sketchCurves.sketchArcs.addByCenterStartSweep(
                    posCSA2,
                    odArc1.endSketchPoint,
                    math.radians(22.8)
                )


                odArc2 = sketch.sketchCurves.sketchArcs.addByCenterStartSweep(
                    pointPrim,
                    posODArc2,
                    math.radians(42.4)
                )

                sketch.sketchCurves.sketchArcs.addByCenterStartSweep(
                    posCSA3,
                    odArc2.startSketchPoint,
                    math.radians(-22.8)
                )

                sketch.sketchCurves.sketchArcs.addByCenterStartSweep(
                    posCSA4,
                    odArc2.endSketchPoint,
                    math.radians(22.8)
                )

                pathLine = sketch.sketchCurves.sketchLines.addByTwoPoints(
                    pointPrim,
                    posLine
                )


                # Creates extude cut with taper
                exturdeInput1 = comp.features.extrudeFeatures.createInput(sketch.profiles[3], 0)
                exturdeInput1.setOneSideExtent(
                    adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString("9 mm")),
                    0,
                    adsk.core.ValueInput.createByString("0 deg")
                )
                f1 = comp.features.extrudeFeatures.add(exturdeInput1)
                
                # Creates extude cut with taper
                exturdeInput2 = comp.features.extrudeFeatures.createInput(sketch.profiles[0], 1)
                exturdeInput2.setOneSideExtent(
                    adsk.fusion.DistanceExtentDefinition.create(adsk.core.ValueInput.createByString("9 mm")),
                    0,
                    adsk.core.ValueInput.createByString("1.72 deg")
                )
                comp.features.extrudeFeatures.add(exturdeInput2)

                # Creates Object collection of both thread wings
                oc = adsk.core.ObjectCollection.create()
                oc.add(sketch.profiles[1])
                oc.add(sketch.profiles[2])

                path = comp.features.createPath(pathLine)
                sweepInput = comp.features.sweepFeatures.createInput(oc, path, 0)
                sweepInput.twistAngle = adsk.core.ValueInput.createByReal(math.radians(648))
                f2 = comp.features.sweepFeatures.add(sweepInput)

                if(des.designType):
                    des.timeline.timelineGroups.add(f1.timelineObject.index-1, f2.timelineObject.index)

            eventArgs.isValidResult = True                
            
        except:
            print(traceback.format_exc())


# Fires when CommandInputs are changed
# Responsible for dynamically updating other Command Inputs
class CommandInputChangedHandler(adsk.core.InputChangedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            if(args.input.id == "DDType"):
                args.inputs.itemById("VIHole").isVisible = not args.input.selectedItem.name[0] == "F"
        except:
            print(traceback.format_exc())
                
                          
# Fires when CommandInputs are changed or other parts of the UI are updated
# Responsible for turning the ok button on or off and allowing preview
class CommandValidateInputsEventHandler(adsk.core.ValidateInputsEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            app = adsk.core.Application.get()
            des = app.activeProduct

            args.areInputsValid = True

            siOrigin = args.inputs.itemById("SIOrigin")
            siPlane = args.inputs.itemById("SIPlane")
            
            if(siOrigin.selectionCount == 1 and siPlane.selectionCount == 0):
                if(not ( siOrigin.selection(0).entity.objectType == "adsk::fusion::SketchPoint" ) or des.designType == 0):
                    args.areInputsValid = False
        except:
            print(traceback.format_exc())


def getPrimitiveFromSelection(selection):
    # Construction Plane
    if selection.objectType == "adsk::fusion::ConstructionPlane":
        # TODO: Coordinate in assembly context, world transform still required!
        return selection.geometry

    # Sketch Profile
    if selection.objectType == "adsk::fusion::Profile":
        return adsk.core.Plane.createUsingDirections(
            selection.parentSketch.origin,
            selection.parentSketch.xDirection,
            selection.parentSketch.yDirection
        )

    # BRepFace
    if selection.objectType == "adsk::fusion::BRepFace":
        _, normal = selection.evaluator.getNormalAtPoint(selection.pointOnFace)
        return adsk.core.Plane.create(
            selection.pointOnFace,
            normal
        )

    # Construction Axis
    if selection.objectType == "adsk::fusion::ConstructionAxis":
        # TODO: Coordinate in assembly context, world transform still required!
        return selection.geometry

    # BRepEdge
    if selection.objectType == "adsk::fusion::BRepEdge":
        # Linear edge
        if (selection.geometry.objectType == "adsk::core::Line3D"):
            _, tangent = selection.evaluator.getTangent(0)
            return adsk.core.InfiniteLine3D.create(
                selection.pointOnEdge,
                tangent
            )
        # Circular edge
        if (selection.geometry.objectType in ["adsk::core::Circle3D", "adsk::core::Arc3D"]):
            return selection.geometry.center

    # Sketch Line
    if selection.objectType == "adsk::fusion::SketchLine":
        return selection.worldGeometry.asInfiniteLine()

    # Construction Point
    if selection.objectType == "adsk::fusion::ConstructionPoint":
        # TODO: Coordinate in assembly context, world transform still required!
        return selection.geometry

    # Sketch Point
    if selection.objectType == "adsk::fusion::SketchPoint":
        return selection.worldGeometry

    # BRepVertex
    if selection.objectType == "adsk::fusion::BRepVertex":
        return selection.geometry


def projectPointOnPlane(point, plane):
    originToPoint = plane.origin.vectorTo(point)

    normal = plane.normal.copy()
    normal.normalize()
    distPtToPln = normal.dotProduct(originToPoint)

    normal.scaleBy(-distPtToPln)

    ptOnPln = point.copy()
    ptOnPln.translateBy(normal)

    return ptOnPln


def run(context):
    try:
        
        app = adsk.core.Application.get()
        ui = app.userInterface
        
        commandDefinitions = ui.commandDefinitions
        #check the command exists or not
        cmdDef = commandDefinitions.itemById(COMMAND_ID)
        if not cmdDef:
            cmdDef = commandDefinitions.addButtonDefinition(COMMAND_ID, COMMAND_NAME,
                                                            COMMAND_TOOLTIP, 'resources')

        ui.allToolbarPanels.itemById("SolidCreatePanel").controls.addCommand(cmdDef, "FusionThreadCommand", False)
        
        onCommandCreated = CommandCreatedHandler()
        cmdDef.commandCreated.add(onCommandCreated)
        _handlers.append(onCommandCreated)
    except:
        print(traceback.format_exc())


def stop(context):
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        
        #Removes the commandDefinition from the toolbar
        p = ui.allToolbarPanels.itemById("SolidCreatePanel").controls.itemById(COMMAND_ID)
        if p:
            p.deleteMe()
        
        #Deletes the commandDefinition
        ui.commandDefinitions.itemById(COMMAND_ID).deleteMe()
            
            
            
    except:
        print(traceback.format_exc())
