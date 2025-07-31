# Copyright 2015 Seth VanHeulen
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

bl_info= {
    "name": "Import MH4U Models",
    "author": "Seth VanHeulen, edited by BlackHazard",
    "version": (1, 3),
    "blender": (4, 4, 0),
    "location": "File > Import > Monster Hunter 4 Ultimate Model (.mod)",
    "description": "Imports a Monster Hunter 4 Ultimate model.",
    "category": "Import-Export",
}

import array
import struct

import bpy


modifier_tables = (
    (2, 8, -2, -8),
    (5, 17, -5, -17),
    (9, 29, -9, -29),
    (13, 42, -13, -42),
    (18, 60, -18, -60),
    (24, 80, -24, -80),
    (33, 106, -33, -106),
    (47, 183, -47, -183)
)


def decode_etc1(image, data):
    data = array.array('I', data)
    image_pixels = [0.0, 0.0, 0.0, 1.0] * image.size[0] * image.size[1]
    block_index = 0
    while len(data) != 0:
        alpha_part1 = 0
        alpha_part2 = 0
        if image.depth == 32:
            alpha_part1 = data.pop(0)
            alpha_part2 = data.pop(0)
        pixel_indices = data.pop(0)
        block_info = data.pop(0)
        bc1 = [0, 0, 0]
        bc2 = [0, 0, 0]
        if block_info & 2 == 0:
            bc1[0] = block_info >> 28 & 15
            bc1[1] = block_info >> 20 & 15
            bc1[2] = block_info >> 12 & 15
            bc1 = [(x << 4) + x for x in bc1]
            bc2[0] = block_info >> 24 & 15
            bc2[1] = block_info >> 16 & 15
            bc2[2] = block_info >> 8 & 15
            bc2 = [(x << 4) + x for x in bc2]
        else:
            bc1[0] = block_info >> 27 & 31
            bc1[1] = block_info >> 19 & 31
            bc1[2] = block_info >> 11 & 31
            bc2[0] = block_info >> 24 & 7
            bc2[1] = block_info >> 16 & 7
            bc2[2] = block_info >> 8 & 7
            bc2 = [x + ((y > 3) and (y - 8) or y) for x, y in zip(bc1, bc2)]
            bc1 = [(x << 3) + (x >> 2) for x in bc1]
            bc2 = [(x << 3) + (x >> 2) for x in bc2]
        flip = block_info & 1
        tcw1 = block_info >> 5 & 7
        tcw2 = block_info >> 2 & 7
        for i in range(16):
            mi = ((pixel_indices >> i) & 1) + ((pixel_indices >> (i + 15)) & 2)
            c = None
            if flip == 0 and i < 8 or flip != 0 and (i // 2 % 2) == 0:
                m = modifier_tables[tcw1][mi]
                c = [max(0, min(255, x + m)) for x in bc1]
            else:
                m = modifier_tables[tcw2][mi]
                c = [max(0, min(255, x + m)) for x in bc2]
            offset = block_index % 4
            x = (block_index - offset) % (image.size[0] // 2) * 2
            y = (block_index - offset) // (image.size[0] // 2) * 8
            if offset & 1:
                x += 4
            if offset & 2:
                y += 4
            x += i // 4
            y += i % 4
            offset = (x + (image.size[1] - y - 1) * image.size[0]) * 4
            image_pixels[offset] = c[0] / 255
            image_pixels[offset+1] = c[1] / 255
            image_pixels[offset+2] = c[2] / 255
        block_index += 1
    image.pixels = image_pixels
    image.update()
    image.pack() #had True inside the brackets, in Blender 4.4 it throws an error, so I just omitted it and works fine


def load_tex(filename, name):
    tex = open(filename, 'rb')
    tex_header = struct.unpack('4s3I', tex.read(16))
    constant = tex_header[1] & 0xfff
    #unknown1 = (tex_header[1] >> 12) & 0xfff
    size_shift = (tex_header[1] >> 24) & 0xf
    #unknown2 = (tex_header[1] >> 28) & 0xf
    mipmap_count = tex_header[2] & 0x3f
    width = (tex_header[2] >> 6) & 0x1fff
    height = (tex_header[2] >> 19) & 0x1fff
    #unknown3 = tex_header[3] & 0xff
    pixel_type = (tex_header[3] >> 8) & 0xff
    #unknown5 = (tex_header[3] >> 16) & 0x1fff
    offsets = array.array('I', tex.read(4 * mipmap_count))
    if pixel_type == 11:
        image = bpy.data.images.new(name, width, height)
        decode_etc1(image, tex.read(width*height//2))
    elif pixel_type == 12:
        image = bpy.data.images.new(name, width, height, alpha=True) #specified alpha since compiler asked for it
        decode_etc1(image, tex.read(width*height))
    tex.close()


def load_mrl():
    pass


def parse_vertex(raw_vertex):
    vertex = array.array('f', raw_vertex[:12])
    uv = array.array('f', raw_vertex[16:24])
    bones = list(raw_vertex[24:26] + raw_vertex[32:33] + raw_vertex[34:35])
    weights = [x / 255 for x in raw_vertex[26:28] + raw_vertex[33:34] + raw_vertex[35:36]]
    return vertex, uv


def parse_faces(vertex_start_index, raw_faces):
    raw_faces = array.array('H', raw_faces)
    reverse = True
    faces = []
    f1 = raw_faces.pop(0)
    f2 = raw_faces.pop(0)
    while len(raw_faces) > 0:
        f3 = raw_faces.pop(0)
        if f3 == 0xffff:
            f1 = raw_faces.pop(0)
            f2 = raw_faces.pop(0)
            reverse = True
        else:
            reverse = not reverse
            if reverse:
                faces.append([f1-vertex_start_index, f3-vertex_start_index, f2-vertex_start_index])
            else:
                faces.append([f1-vertex_start_index, f2-vertex_start_index, f3-vertex_start_index])
            f1 = f2
            f2 = f3
    return faces


def build_uv_map(b_mesh, uvs, faces):
    #b_mesh.uv_textures.new() This is now renamed to uv_layers in Blender 4.4 's API
    b_mesh.uv_layers.new()
    for i,loop in enumerate(b_mesh.loops):
        b_mesh.uv_layers[0].data[i].uv = uvs[loop.vertex_index]


def load_mod(filename, context, material_to_apply):
    mod = open(filename, 'rb')
    mod_header = struct.unpack('4s4H13I', mod.read(64))
    if mod_header[0] != b'MOD\x00' or mod_header[1] != 0xe6:
        mod.close()
        return
    parentObject = bpy.data.objects.new(filename[(filename.rfind("\\") + 1):], None )
    bpy.context.collection.objects.link(parentObject)
    for i in range(mod_header[3]):
        mod.seek(mod_header[15] + i * 48)
        mesh_info = struct.unpack('HHIHBB9I', mod.read(48))
        mod.seek(mod_header[16] + mesh_info[6] * mesh_info[4] + mesh_info[7])
        vertices = []
        uvs = []
        for j in range(mesh_info[1]):
            vertex, uv = parse_vertex(mod.read(mesh_info[4]))
            vertices.append(vertex)
            if len(uv) != 0:
                uvs.append(uv)
        mod.seek(mod_header[17] + mesh_info[9] * 2)
        faces = parse_faces(mesh_info[6], mod.read(mesh_info[10] * 2 + 2))
        b_mesh = bpy.data.meshes.new('imported_mesh_{}'.format(i))
        b_object = bpy.data.objects.new('imported_object_{}'.format(i), b_mesh)
        b_mesh.from_pydata(vertices, [], faces)
        b_mesh.update(calc_edges=True)
        b_object.data.materials.append(material_to_apply)
        b_object.active_material_index = len(b_object.data.materials) - 1
        #bpy.context.scene.objects.link(b_object) 
        #this now looks like this:
        bpy.context.collection.objects.link(b_object)
        b_object.parent = parentObject
        if len(uvs) != 0:
            build_uv_map(b_mesh, uvs, faces)
    mod.close()

#calls load_tex on all .tex files that are in the directory
def multitex_loader(filepath, mod_type):
    from pathlib import Path
    import os
    suffix = os.path.splitext(os.path.basename(filepath))[0]
    if(mod_type == 'Enemy'):
        #opens the mod file to check for how many textures/materials are needed
        mod = open(filepath, 'rb')
        mod_header = struct.unpack('4s4H13I', mod.read(64))
        if mod_header[0] != b'MOD\x00' or mod_header[1] != 0xe6:
            mod.close()
            return
        #gets the number of "XfB"
        n_textures = mod_header[4]
        for i in range(n_textures):
            my_file = Path(filepath.replace('.mod', ('_0' + str(i) + '_BM.tex')))
            if my_file.is_file():
                #offset is given
                mod.seek(mod_header[14] + 128*i)
                name_bytes = struct.unpack('30s', mod.read(30))
                name = ""
                #gets from the read tuple the string
                for byted in name_bytes:
                    name += byted.decode('utf-8')
            
                #if the xfb is body, we keep it for later. The body always gets the 01 texture
                if "body" in name:
                    name = "Body"
                    load_tex(filepath.replace('.mod', ('_01' + '_BM.tex')), suffix + name)
                #lazy solution to the fact that the body never is the first xfb mentioned...
                elif i==1 and not "body" in name:
                    load_tex(filepath.replace('.mod', ('_0' + str(i + 1) + '_BM.tex')), suffix + name)
                    createMaterial(suffix+name)
                else:
                    load_tex(filepath.replace('.mod', ('_0' + str(i) + '_BM.tex')), suffix + name)
                    createMaterial(suffix+name)
        mod.close()
            #checks for normals in the folder
        for i in range(n_textures):
            my_file = Path(filepath.replace('.mod', ('_0' + str(i) + '_NM_MIRROR.tex')))
            if my_file.is_file():
                load_tex(filepath.replace('.mod', ('_0' + str(i) + '_NM_MIRROR.tex')), str(i) + 'NM_MIRROR')
    elif(mod_type == 'Armor'):
        name = "Body"
        load_tex(filepath.replace('.mod', ('_BM.tex')), suffix + name)
    else:
        print("Unsupported Operation")


def createMaterial(texture_name, normal_name = ""):
    tex_material = bpy.data.materials.new(name=(texture_name + "Material"))
    tex_material.use_nodes = True
    principled_bsdf = tex_material.node_tree.nodes["Principled BSDF"]
    if texture_name:
        texture = tex_material.node_tree.nodes.new("ShaderNodeTexImage")
        try:
            texture.image = bpy.data.images[texture_name]
            tex_material.node_tree.links.new(principled_bsdf.inputs["Base Color"], texture.outputs['Color'])
        except:
            print("Texture " + texture_name + " not found.")
    #if normal_name #missing normal support right now
    return tex_material


from bpy_extras.io_utils import ImportHelper #needed to get the filepath correctly in Blender 4.4
class IMPORT_OT_mod(bpy.types.Operator, ImportHelper):
    bl_idname = "import_scene.mod"
    bl_label = "Import MOD"
    bl_description = "Import a Monster Hunter 4 Ultimate model"
    bl_options = {"REGISTER", "UNDO"}
    texture_import: bpy.props.BoolProperty(
                                name="Import textures", 
                                default = True, 
                                description="If checked, imports all textures of the .MOD file and applies some of them to the model")
    mod_type: bpy.props.EnumProperty(
                            items=[('Enemy', "Monster", "If the MOD File contains a monster"),
                                   ('Armor', "Armor", "If the MOD File contains an armor"),
                                   ('Other', "OTHER", "NOT SUPPORTED") ],
                            name="MOD File Type",
                            #default="Enemy",
                            description="What the MOD file contains. Not needed if Import textures is not checked")
    
    #filepath = bpy.props.StringProperty(name="File Path", description="Filepath used for importing the MOD file", maxlen=1024, default="") 
    #In Blender 4.4, this line of code later throws an error, saying that it's _PropertyDeferred and not string. Since it wasn't used anywhere else in the scope, I moved the variable in the execute function

    def execute(self, context):
        import os
        filepath = self.properties.filepath
        mrl_name = ""
        if self.texture_import:
            mrl_name = os.path.splitext(os.path.basename(filepath))[0] + "Body"
            multitex_loader(self.filepath, self.mod_type)
        load_mod(self.filepath, context, createMaterial(mrl_name))
        #load_tex(self.filepath.replace('.58A15856', '_BM.241F5DEB'), 'test') 
        #This line of code doesn't look like to load the files in the directory, maybe because I used a different arc unzipper? Should look into svan's arc.py file
        #I've made a little function that checks for all textures in the folder and loads them in the editor
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        wm.fileselect_add(self)
        return {'RUNNING_MODAL'}


def menu_func(self, context):
    self.layout.operator(IMPORT_OT_mod.bl_idname, text="Monster Hunter 4 Ultimate Model (.mod)")

classes = (
    IMPORT_OT_mod,
)

def register():
    #Register modules don't exist anymore in Blender 4.4 API
    #bpy.utils.register_module(__name__)
    #This function is now called TOPBAR
    #bpy.types.INFO_MT_file_import.append(menu_func)
    bpy.types.TOPBAR_MT_file_import.append(menu_func)
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)


def unregister():
    #bpy.utils.unregister_module(__name__)
    #bpy.types.INFO_MT_file_import.remove(menu_func)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func)
    from bpy.utils import unregister_class
    for cls in classes:
        unregister_class(cls)


if __name__ == "__main__":
    register()
